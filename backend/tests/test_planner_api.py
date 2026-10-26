from copy import deepcopy
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import json
import os
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.main import app
from app import planner_api
from app.food_models import Food, NutritionSnapshot
from app.food_source import convert_row
from app.meal_constraints import MealConstraints
from app.planner_contracts import PlanRequest
from app.planner_models import MealPlan, PlanOperation
from app.planner_service import build_meals, day_menu_families, menu_catalog, menu_definitions, name_matches
from app.preference_contracts import SettingsRequest
from app.session_dependency import get_session

CASES = json.loads((Path(__file__).parent / 'fixtures/planner-api-cases.json').read_text(encoding='utf-8'))['cases']
FIELDS = ('energy_kcal', 'protein_g', 'fat_g', 'carbohydrate_g')


class Flow:
    def __init__(self, client, session):
        self.client = client
        self.session = session
        self.log = []
        self.outputs = {}
        self.menus = menu_catalog(session)
        self.by_id = {menu['menu_id']: menu for menu in self.menus}

    def request(self, method, path, body=None, status=200, params=None):
        response = self.client.request(method, path, **({'json': body} if body is not None else {}), params=params)
        try:
            data = response.json()
        except ValueError:
            data = response.text
        self.log.append({'method': method, 'path': path, 'body': body, 'params': params,
                         'status': response.status_code, 'response': data})
        assert response.status_code == status, (method, path, response.status_code, response.text)
        return data

    def create(self, case, **overrides):
        body = {**deepcopy(case['plan']), 'client_request_id': str(uuid4()), **overrides}
        plan = self.request('POST', '/api/plans', body, status=201)
        return plan, body

    def change(self, plan, key, action, status=200, **values):
        body = {'client_request_id': str(uuid4()), 'expected_version': plan['version'],
                'meal_key': key, 'action': action, **values}
        return self.request('PATCH', '/api/plans/' + plan['id'], body, status=status), body

    def meal(self, plan, key):
        return next(meal for meal in plan['meals'] if meal['key'] == key)

    def named(self, name):
        return next(menu for menu in self.menus if menu['name'] == name)

    def preserved(self, before, after, changed_key):
        assert [meal for meal in before['meals'] if meal['key'] != changed_key] == [meal for meal in after['meals'] if meal['key'] != changed_key]


@pytest.fixture
def flow(test_engine):
    with test_engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection, join_transaction_mode='create_savepoint') as session:
            app.dependency_overrides[get_session] = lambda: session
            try:
                definitions = menu_definitions()
                snapshot_id = uuid4().hex
                session.execute(update(NutritionSnapshot).values(active=False))
                session.add(NutritionSnapshot(id=snapshot_id, source_url=definitions['source_url'],
                    retrieved_at=datetime.now(timezone.utc), row_count=len(definitions['reference_rows']),
                    active=True, manifest={'test_subset': True, 'catalog_version': definitions['version']}))
                session.flush()
                for row in definitions['reference_rows']:
                    session.add(Food(**convert_row(row, snapshot_id)))
                session.flush()
                with TestClient(app) as client:
                    yield Flow(client, session)
            finally:
                app.dependency_overrides.clear()
        transaction.rollback()


def check_totals(plan):
    for meal in plan['meals']:
        if not meal['items']:
            continue
        for field in FIELDS:
            known = [Decimal(item['nutrients'][field]) for item in meal['items'] if item['nutrients'][field] is not None]
            assert meal['nutrients'][field] is None if not known else Decimal(meal['nutrients'][field]) == sum(known)
    for field in FIELDS:
        known = [Decimal(item['nutrients'][field]) for meal in plan['meals'] for item in meal['items'] if item['nutrients'][field] is not None]
        assert plan['nutrients'][field] is None if not known else Decimal(plan['nutrients'][field]) == sum(known)


def run_case(case, flow, monkeypatch):
    key = case['id']
    settings = flow.request('PUT', '/api/preferences', case['settings'])
    assert len(flow.menus) == 136
    plan, body = flow.create(case)
    flow.outputs['initial_plan'] = deepcopy(plan)
    if key == 'P01':
        assert [meal['key'] for meal in plan['meals']] == ['breakfast', 'lunch', 'dinner']
        assert all(meal['items'] for meal in plan['meals']) and not plan['missing_nutrients']
        for meal in plan['meals']:
            for item in meal['items']:
                assert Decimal(item['min_g']) <= Decimal(item['amount_g']) <= Decimal(item['max_g'])
                for field in FIELDS:
                    assert Decimal(item['nutrients'][field]) == (Decimal(item['reference_nutrients'][field]) * Decimal(item['amount_g']) / 100).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
        check_totals(plan)
        assert Decimal(plan['target_difference']['energy_kcal']) == Decimal(plan['nutrients']['energy_kcal']) - Decimal('1800')
    elif key == 'P02':
        snack = flow.meal(plan, 'snack')
        assert snack['items'] and all('간식' in flow.by_id[item['menu_id']]['meal_slots'] for item in snack['items'])
        assert all('구이' not in item['name'] for item in snack['items'])
        for item in snack['items']:
            assert Decimal(item['min_g']) <= Decimal(item['amount_g']) <= Decimal(item['max_g'])
        check_totals(plan)
    elif key == 'P03':
        families = [day_menu_families(meal['items']) for meal in plan['meals']]
        assert all(not left & right for index, left in enumerate(families) for right in families[index + 1:])
        assert sum('main:비빔밥' in group for group in families) == 1
        assert all(not name_matches(flow.by_id[item['menu_id']], ['생선']) for meal in plan['meals'] for item in meal['items'])
        assert any('선호·평소 음식' in meal['reason'] for meal in plan['meals'])
    elif key == 'P04':
        assert all(flow.by_id[item['menu_id']]['ready_to_eat'] for item in flow.meal(plan, 'breakfast')['items'])
        for meal in plan['meals']:
            assert all(not name_matches(flow.by_id[item['menu_id']], ['생선']) for item in meal['items'])
        lunch, dinner = flow.meal(plan, 'lunch'), flow.meal(plan, 'dinner')
        assert lunch['minutes'] <= 15 and dinner['minutes'] <= 30
        assert all(not name_matches(flow.by_id[item['menu_id']], ['버섯']) for item in lunch['items'])
        assert all(flow.by_id[item['menu_id']]['preparation_mode'] not in ['pot', 'steam', 'blanch', 'grill', 'heat'] for item in dinner['items'])
        assert flow.request('GET', '/api/preferences') == settings
    elif key == 'P05':
        locked, _ = flow.change(plan, 'breakfast', 'lock', locked=True)
        updated, _ = flow.change(locked, 'lunch', 'replace')
        flow.preserved(locked, updated, 'lunch')
        assert flow.meal(updated, 'breakfast')['locked']
        flow.change(updated, 'breakfast', 'replace', status=409)
        assert flow.request('GET', '/api/plans/' + plan['id']) == updated
    elif key == 'P06':
        for slot, value in body['fixed_meals'].items():
            meal = flow.meal(plan, slot)
            assert meal['locked'] and meal['items'][0]['menu_id'] == value['menu_id'] and meal['items'][0]['amount_g'] == '300'
        assert any('비빔밥 계열이 겹쳐요' in note for note in plan['notes'])
    elif key == 'P07':
        tuna = flow.named('샌드위치 · 참치')
        before = deepcopy(plan)
        listed = flow.request('GET', '/api/planner/menus', params=[('q', '샌드위치'), ('avoided_foods', '생선')])
        assert next(menu for menu in listed['items'] if menu['menu_id'] == tuna['menu_id'])['excluded_by'] == ['생선']
        warning = flow.request('GET', '/api/planner/menu-exclusion-check', params=[('menu_id', tuna['menu_id']), ('avoided_foods', '생선')])
        assert warning['conflicts'] == ['생선']
        assert flow.request('GET', '/api/plans/' + plan['id']) == before
        updated, _ = flow.change(plan, 'lunch', 'set', menu_id=tuna['menu_id'], amount_g='200')
        flow.preserved(before, updated, 'lunch')
        assert flow.request('GET', '/api/preferences') == settings
        replaced, _ = flow.change(updated, 'lunch', 'replace')
        assert all(not name_matches(flow.by_id[item['menu_id']], ['생선']) for item in flow.meal(replaced, 'lunch')['items'])
    elif key == 'P08':
        roles = {role: next(menu for menu in flow.menus if menu['role'] == role) for role in ['staple', 'protein', 'soup']}
        assembled, _ = flow.change(plan, 'dinner', 'set', menu_id=roles['staple']['menu_id'], amount_g='150')
        assembled, _ = flow.change(assembled, 'dinner', 'add', menu_id=roles['protein']['menu_id'], amount_g='80')
        assembled, _ = flow.change(assembled, 'dinner', 'add', menu_id=roles['soup']['menu_id'], amount_g='100')
        assembled, _ = flow.change(assembled, 'dinner', 'lock', locked=True)
        items = deepcopy(flow.meal(assembled, 'dinner')['items'])
        changed, _ = flow.change(assembled, 'dinner', 'update_item', item_id=items[1]['item_id'], custom_name='집에서 준비한 반찬', amount_g=None)
        actual = flow.meal(changed, 'dinner')['items']
        assert actual[0] == items[0] and actual[2] == items[2]
        assert actual[1]['name'] == '집에서 준비한 반찬' and actual[1]['amount_g'] is None
        assert all(value is None for value in actual[1]['nutrients'].values())
        assert flow.meal(changed, 'dinner')['locked']
        flow.preserved(assembled, changed, 'dinner')
        check_totals(changed)
        assert changed['target_difference']['energy_kcal'] is None
        flow.outputs['set_before'], flow.outputs['set_after'] = assembled, changed
    elif key == 'P09':
        selected, _ = flow.change(plan, 'lunch', 'set', menu_id=flow.named('비빔밥')['menu_id'], amount_g='300')
        before = deepcopy(flow.meal(selected, 'lunch')['items'][0])
        updated, _ = flow.change(selected, 'lunch', 'portion', item_id=before['item_id'], amount_g='450')
        after = flow.meal(updated, 'lunch')['items'][0]
        assert after['food'] == before['food'] and after['reference_nutrients'] == before['reference_nutrients']
        for field in FIELDS:
            assert Decimal(after['nutrients'][field]) == (Decimal(before['reference_nutrients'][field]) * Decimal('4.5')).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
        flow.preserved(selected, updated, 'lunch')
        flow.change(updated, 'lunch', 'portion', status=422, item_id=after['item_id'], amount_g=None)
        assert flow.request('GET', '/api/plans/' + plan['id']) == updated
        check_totals(updated)
    elif key == 'P10':
        updated, _ = flow.change(plan, 'lunch', 'set', custom_name='오늘 준비한 도시락', amount_g=None)
        meal = flow.meal(updated, 'lunch')
        assert meal['items'][0]['amount_g'] is None and all(value is None for value in meal['nutrients'].values())
        assert not meal['locked'] and meal['items'][0]['food'] is None
        assert set(updated['missing_nutrients']) == set(FIELDS) and updated['target_difference']['energy_kcal'] is None
        flow.preserved(plan, updated, 'lunch')
        check_totals(updated)
    elif key == 'P11':
        updated, replacement = flow.change(plan, 'lunch', 'replace')
        assert flow.meal(updated, 'lunch')['items'] != flow.meal(plan, 'lunch')['items']
        flow.preserved(plan, updated, 'lunch')
        restored, _ = flow.change(updated, 'lunch', 'undo_replace', replacement_request_id=replacement['client_request_id'])
        assert restored['meals'] == plan['meals'] and restored['version'] > updated['version']
        again, replacement = flow.change(restored, 'lunch', 'replace')
        manual, _ = flow.change(again, 'lunch', 'set', custom_name='내가 고른 점심')
        flow.change(manual, 'lunch', 'undo_replace', status=409, replacement_request_id=replacement['client_request_id'])
        assert flow.request('GET', '/api/plans/' + plan['id']) == manual
    elif key == 'P12':
        assert flow.request('POST', '/api/plans', body) == plan
        flow.request('POST', '/api/plans', {**body, 'energy_target': '2100'}, status=409)
        before_count = flow.session.scalar(select(func.count()).select_from(PlanOperation))
        updated, edit = flow.change(plan, 'lunch', 'replace')
        assert flow.request('PATCH', '/api/plans/' + plan['id'], edit) == updated
        assert flow.session.scalar(select(func.count()).select_from(PlanOperation)) == before_count + 1
        flow.request('PATCH', '/api/plans/' + plan['id'], {**edit, 'client_request_id': str(uuid4())}, status=409)
        assert flow.request('GET', '/api/plans/' + plan['id']) == updated
    elif key == 'P13':
        password = 'Local-test-password-2026'
        user_a = flow.client.post('/api/auth/register', json={'username': 'test_a_' + uuid4().hex[:8], 'password': password}).json()['user']
        own, _ = flow.create(case, fixed_meals={'lunch': {'custom_name': '소유자A만의점심'}})
        with TestClient(app) as other:
            user_b = other.post('/api/auth/register', json={'username': 'test_b_' + uuid4().hex[:8], 'password': password}).json()['user']
            assert all(item['id'] != own['id'] for item in other.get('/api/plans').json())
            assert other.get('/api/plans/' + own['id']).status_code == 404
            assert other.patch('/api/plans/' + own['id'], json={'expected_version': own['version'], 'meal_key': 'lunch', 'action': 'lock', 'locked': False}).status_code == 404
            assert planner_api.recent_plan_meals(flow.session, 'u:' + user_b['id']) == {}
        with TestClient(app) as guest:
            assert guest.get('/api/plans/' + own['id']).status_code == 404
            assert all(item['id'] != own['id'] for item in guest.get('/api/plans').json())
        assert planner_api.recent_plan_meals(flow.session, 'u:' + user_a['id'])
        flow.outputs['ownership'] = {'account_b_and_guest_read_write_denied': True, 'other_owner_recent_history_empty': True}
    elif key == 'P14':
        breakfast = flow.meal(plan, 'breakfast')
        assert breakfast['status'] == 'empty' and not breakfast['items'] and plan['missing_nutrients']
        tiny = [flow.named('삶은 달걀')]
        request = PlanRequest(plan_date=date(2026, 10, 26), meal_count=4)
        first = build_meals(request, tiny, SettingsRequest(), {})
        second = build_meals(request, tiny, SettingsRequest(), {}, {'snack': [first[3]] * 5})
        assert second[3]['items'] and [item['menu_id'] for item in first[3]['items']] == [item['menu_id'] for item in second[3]['items']]
        assert '같은 메뉴가 다시 나올 수 있어요' in second[3]['reason']
        flow.outputs['tiny_catalog_first'], flow.outputs['tiny_catalog_repeat'] = first, second
    elif key == 'P15':
        snapshot = flow.session.scalar(select(NutritionSnapshot).where(NutritionSnapshot.active.is_(True)))
        row = deepcopy(menu_definitions()['reference_rows'][0])
        synthetic_ids = []
        for index, (name, basis) in enumerate([('열무 비빔밥', '100g'), ('비빔밥_열무', '100ml')]):
            data = convert_row({**row, 'FOOD_CD': 'TEST-' + uuid4().hex, 'FOOD_NM': name,
                                'NUT_CON_SRTR_QUA': basis, 'COMPANY_NM': None}, snapshot.id)
            synthetic_ids.append(data['id'])
            flow.session.add(Food(**data))
        flow.session.flush()
        groups = flow.request('GET', '/api/food-groups', params={'q': '비빔밥', 'limit': 50})
        assert groups['total'] < groups['source_total']
        group = next(group for group in groups['groups'] if group['name'] == '비빔밥 · 열무' and group['company'] is None)
        values = [variant for variant in group['variants'] if variant['id'] in synthetic_ids]
        assert len(values) == 2 and {variant['basis_unit'] for variant in values} == {'g', 'mL'}
        assert group['selected']['basis_unit'] == 'g'
        for variant in values:
            assert variant['source']['snapshot_id'] == snapshot.id
    elif key == 'P16':
        before_count = flow.session.scalar(select(func.count()).select_from(MealPlan))
        monkeypatch.setattr(planner_api, 'menu_catalog', lambda session: [])
        flow.request('POST', '/api/plans', {**body, 'client_request_id': str(uuid4())}, status=503)
        assert flow.session.scalar(select(func.count()).select_from(MealPlan)) == before_count
        assert flow.request('GET', '/api/plans/' + plan['id']) == plan
        assert flow.request('GET', '/api/preferences') == settings
    else:
        raise AssertionError(key)


@pytest.mark.parametrize('case', CASES, ids=lambda case: case['id'])
def test_planner_scenario(case, flow, monkeypatch, tmp_path):
    status = 'failed'
    error = None
    try:
        run_case(case, flow, monkeypatch)
        status = 'passed'
    except Exception as problem:
        error = {'type': type(problem).__name__, 'message': str(problem)}
        raise
    finally:
        directory = Path(os.environ.get('ONEUL_TEST_EVIDENCE', str(tmp_path)))
        directory.mkdir(parents=True, exist_ok=True)
        (directory / (case['id'] + '.json')).write_text(json.dumps({'case': case['id'], 'title': case['title'], 'status': status,
             'error': error, 'requests': flow.log, 'outputs': flow.outputs}, ensure_ascii=False, indent=2), encoding='utf-8')
