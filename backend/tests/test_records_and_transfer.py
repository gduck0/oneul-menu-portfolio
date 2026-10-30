from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import event, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.main import app
from app.personal_models import GuestTransfer, MealChange, MealEntry, MenuFeedback, PersonalSettings
from app.personal_ranking import rating_scores
from app.planner_models import MealPlan
from app.security import GUEST_COOKIE, token_hash
from app.session_dependency import get_session
from test_planner_api import CASES, flow


def now():
    return datetime.now(timezone.utc).isoformat()


def meal(client, **values):
    response = client.post('/api/meals', json={'name': '직접 남긴 식사', 'eaten_at': now(),
        'client_record_id': str(uuid4()), **values})
    assert response.status_code == 201, response.text
    return response.json()


def register(client):
    credentials = {'username': 'test_' + uuid4().hex[:12], 'password': 'Local-test-password-2026'}
    response = client.post('/api/auth/register', json=credentials)
    assert response.status_code == 201, response.text
    return response.json()['user'], credentials


def record(client, plan, **changes):
    key = plan['meals'][0]['key']
    body = {'client_record_id': str(uuid4()), 'expected_version': plan['version'], 'eaten_at': now(), **changes}
    response = client.post(f"/api/plans/{plan['id']}/meals/{key}/record", json=body)
    assert response.status_code == 200, response.text
    return response.json(), body


@pytest.fixture(autouse=True)
def evidence(flow, monkeypatch, request, tmp_path):
    requests = []
    original = TestClient.request

    def logged(client, method, url, **kwargs):
        response = original(client, method, url, **kwargs)
        body = deepcopy(kwargs.get('json'))
        if isinstance(body, dict) and 'password' in body:
            body['password'] = '[test password omitted]'
        requests.append({'method': method, 'path': str(url), 'body': body,
            'status': response.status_code, 'response': response.json() if response.content else None})
        return response

    monkeypatch.setattr(TestClient, 'request', logged)
    yield
    directory = Path(os.environ.get('ONEUL_TEST_EVIDENCE', str(tmp_path)))
    directory.mkdir(parents=True, exist_ok=True)
    (directory / (request.node.name + '.json')).write_text(json.dumps({'test': request.node.name,
        'requests': requests}, ensure_ascii=False, indent=2), encoding='utf-8')


def test_catalog_record_recalculates_and_retry_is_idempotent(flow):
    food_id = flow.named('비빔밥')['food']['id']
    body = {'client_record_id': str(uuid4()), 'food_id': food_id, 'portion': {'amount': '123.45', 'unit': 'g'}, 'eaten_at': now()}
    first = flow.request('POST', '/api/meals', body, status=201)
    expected = flow.request('GET', f'/api/foods/{food_id}/nutrition', params={'amount': '123.45', 'unit': 'g'})
    assert first['nutrients'] == expected['nutrients'] and first['nutrition_source'] == 'catalog'
    assert flow.request('POST', '/api/meals', body) == first
    flow.request('POST', '/api/meals', {**body, 'portion': {'amount': '150', 'unit': 'g'}}, status=409)
    assert flow.request('GET', '/api/meals')['total'] == 1
    assert flow.request('GET', '/api/meals/' + first['id']) == first


def test_unknown_record_retry_feedback_and_edit_keep_missing_values(flow):
    saved = meal(flow.client)
    assert saved['portion'] is None and all(value is None for value in saved['nutrients'].values())
    body = {'phase': 'consumed', 'context_id': saved['id'], 'food_id': None, 'rating': 'like', 'reason': 'taste'}
    first = flow.request('PUT', '/api/feedback', body)
    assert flow.request('PUT', '/api/feedback', body)['id'] == first['id']
    assert len(flow.request('GET', '/api/feedback')) == 1
    row = flow.session.get(MenuFeedback, first['id'])
    assert row.food_code is None and rating_scores(flow.session, row.owner_key) == {}
    edited = flow.request('PATCH', '/api/meals/' + saved['id'], {'expected_version': saved['version'],
        'portion': None, 'eaten_at': saved['eaten_at']})['meal']
    assert edited['portion'] is None and edited['nutrition'] is None


@pytest.mark.parametrize('reason', [None, 'portion', 'unavailable', 'purpose', 'variety'])
def test_non_taste_feedback_never_changes_planner_scores(flow, reason):
    menu = flow.named('비빔밥')
    saved = meal(flow.client, name=None, food_id=menu['food']['id'], portion={'amount': '200', 'unit': 'g'})
    body = {'phase': 'consumed', 'context_id': saved['id'], 'food_id': saved['food_id'], 'reason': reason}
    for rating in ['like', 'dislike', 'neutral']:
        feedback = flow.request('PUT', '/api/feedback', {**body, 'rating': rating})
        owner = flow.session.get(MenuFeedback, feedback['id']).owner_key
        assert rating_scores(flow.session, owner) == {}
        assert flow.session.get(MenuFeedback, feedback['id']).reason == reason


def test_taste_feedback_updates_cancels_and_restores_scores(flow):
    menu = flow.named('비빔밥')
    saved = meal(flow.client, name=None, food_id=menu['food']['id'], portion={'amount': '200', 'unit': 'g'})
    body = {'phase': 'consumed', 'context_id': saved['id'], 'food_id': saved['food_id'], 'reason': 'taste'}
    previous = None
    for rating, expected in [('like', '.06'), ('dislike', '-.06'), ('neutral', '0'), ('like', '.06')]:
        feedback = flow.request('PUT', '/api/feedback', {**body, 'rating': rating})
        assert previous in [None, feedback['id']]
        previous = feedback['id']
        owner = flow.session.get(MenuFeedback, feedback['id']).owner_key
        assert rating_scores(flow.session, owner)[menu['source_selected_code']] == Decimal(expected)
    cancelled = flow.request('POST', '/api/meals/' + saved['id'] + '/cancel', {'expected_version': 1})['meals'][0]
    assert rating_scores(flow.session, owner) == {}
    flow.request('PUT', '/api/feedback', {**body, 'rating': 'like'}, status=404)
    flow.request('POST', '/api/meals/' + saved['id'] + '/restore', {'expected_version': cancelled['version']})
    assert rating_scores(flow.session, owner)[menu['source_selected_code']] == Decimal('.06')
    flow.request('DELETE', '/api/feedback/' + previous, status=204)
    assert rating_scores(flow.session, owner) == {}


def test_feedback_validation_and_owner_isolation(flow):
    saved = meal(flow.client)
    feedback = {'phase': 'consumed', 'context_id': saved['id'], 'food_id': None, 'rating': 'like', 'reason': 'taste'}
    first = flow.request('PUT', '/api/feedback', feedback)
    with TestClient(app) as other:
        assert other.put('/api/feedback', json=feedback).status_code == 404
        assert other.get('/api/feedback').json() == []
        assert other.delete('/api/feedback/' + first['id']).status_code == 404
        for action in ['cancel', 'restore']:
            assert other.post('/api/meals/' + saved['id'] + '/' + action, json={'expected_version': 1}).status_code == 404
        assert other.get('/api/meals/' + saved['id']).status_code == 404
    flow.request('PUT', '/api/feedback', {**feedback, 'food_id': flow.named('비빔밥')['food']['id']}, status=422)
    flow.request('PUT', '/api/feedback', {**feedback, 'phase': 'recommendation'}, status=404)
    assert len(flow.request('GET', '/api/feedback')) == 1


def test_actual_record_preserves_planned_amount_and_rejects_repeat(flow):
    plan, _ = flow.create(CASES[0])
    planned = deepcopy(plan['meals'][0])
    amount = str((Decimal(planned['items'][0]['amount_g']) / 2).quantize(Decimal('.01')))
    saved, body = record(flow.client, plan, amounts={planned['items'][0]['item_id']: amount})
    assert saved['records'][0]['portion']['amount'] == amount
    assert saved['plan']['meals'][0]['items'] == planned['items']
    assert flow.request('POST', f"/api/plans/{plan['id']}/meals/breakfast/record", body) == saved
    flow.request('PATCH', '/api/plans/' + plan['id'], {'expected_version': saved['plan']['version'],
        'meal_key': 'breakfast', 'action': 'replace'}, status=409)
    flow.request('POST', f"/api/plans/{plan['id']}/meals/breakfast/record", {**body,
        'client_record_id': str(uuid4()), 'expected_version': saved['plan']['version']}, status=409)


@pytest.mark.parametrize('include_settings,account_settings', [(True, False), (True, True), (False, False), (False, True)])
def test_explicit_transfer_settings_policy_and_retry(flow, include_settings, account_settings):
    flow.request('PUT', '/api/preferences', {'favorite_foods': ['김밥']})
    plan, _ = flow.create(CASES[0])
    saved, _ = record(flow.client, plan)
    entry = saved['records'][0]
    feedback = flow.request('PUT', '/api/feedback', {'phase': 'consumed', 'context_id': entry['id'],
        'food_id': entry['food_id'], 'rating': 'like', 'reason': 'taste'})
    guest_owner = flow.session.get(MealPlan, plan['id']).owner_key
    with TestClient(app) as account:
        user, credentials = register(account)
        if account_settings:
            assert account.put('/api/preferences', json={'favorite_foods': ['두부']}).status_code == 200
    flow.request('POST', '/api/auth/login', credentials)
    assert flow.request('GET', '/api/plans') == []
    assert flow.request('GET', '/api/meals')['total'] == 0
    summary = flow.request('GET', '/api/guest-data')
    assert summary['plans'] == 1 and summary['meals'] == len(saved['records']) and summary['settings']
    request = {'client_request_id': str(uuid4()), 'include_settings': include_settings}
    result = flow.request('POST', '/api/guest-data/import', request)
    assert result['settings_imported'] == (include_settings and not account_settings)
    assert result['settings_kept'] == (include_settings and account_settings)
    assert flow.request('POST', '/api/guest-data/import', request) == result
    flow.request('POST', '/api/guest-data/import', {**request, 'include_settings': not include_settings}, status=409)
    expected = ['두부'] if account_settings else ['김밥'] if include_settings else []
    assert flow.request('GET', '/api/preferences')['favorite_foods'] == expected
    assert flow.request('GET', '/api/plans/' + plan['id'])['id'] == plan['id']
    assert flow.request('GET', '/api/feedback')[0]['id'] == feedback['id']
    assert flow.session.get(MealEntry, entry['id']).owner_key == 'u:' + user['id']
    assert flow.session.get(PersonalSettings, guest_owner).payload['favorite_foods'] == ['김밥']
    flow.request('POST', '/api/auth/logout', {}, status=204)
    assert flow.request('GET', '/api/plans') == [] and flow.request('GET', '/api/meals')['total'] == 0
    flow.request('POST', '/api/auth/login', credentials)
    assert flow.request('GET', '/api/meals')['total'] == len(saved['records'])


@pytest.mark.parametrize('kind', ['plan', 'meal', 'change'])
def test_transfer_request_collisions_preserve_both_owners(flow, kind):
    request_id = str(uuid4())
    plan, _ = flow.create(CASES[0], client_request_id=request_id)
    guest_meal = meal(flow.client, client_record_id=request_id)
    if kind == 'change':
        flow.request('PATCH', '/api/meals/' + guest_meal['id'], {'client_request_id': request_id,
            'expected_version': 1, 'portion': None, 'eaten_at': guest_meal['eaten_at']})
    guest_owner = flow.session.get(MealPlan, plan['id']).owner_key
    with TestClient(app) as account:
        user, credentials = register(account)
        if kind == 'plan':
            assert account.post('/api/plans', json={**CASES[0]['plan'], 'client_request_id': request_id}).status_code == 201
        else:
            account_meal = meal(account, client_record_id=request_id if kind == 'meal' else str(uuid4()))
            if kind == 'change':
                assert account.patch('/api/meals/' + account_meal['id'], json={'client_request_id': request_id,
                    'expected_version': 1, 'portion': None, 'eaten_at': account_meal['eaten_at']}).status_code == 200
    flow.request('POST', '/api/auth/login', credentials)
    before = {model.__name__: flow.session.scalar(select(func.count()).select_from(model)) for model in [MealPlan, MealEntry, MealChange, GuestTransfer]}
    flow.request('POST', '/api/guest-data/import', {}, status=409)
    flow.session.expire_all()
    assert flow.session.get(MealPlan, plan['id']).owner_key == guest_owner
    assert flow.session.get(MealEntry, guest_meal['id']).owner_key == guest_owner
    assert before == {model.__name__: flow.session.scalar(select(func.count()).select_from(model)) for model in [MealPlan, MealEntry, MealChange, GuestTransfer]}


def test_stale_guest_cookie_cannot_write_after_transfer(flow):
    meal(flow.client)
    old_cookie = flow.client.cookies.get(GUEST_COOKIE)
    user, _ = register(flow.client)
    request = {'client_request_id': str(uuid4())}
    result = flow.request('POST', '/api/guest-data/import', request)
    with TestClient(app) as stale:
        stale.cookies.set(GUEST_COOKIE, old_cookie, domain='testserver.local', path='/')
        assert stale.post('/api/meals', json={'name': '중복 체험 기록', 'eaten_at': now()}).status_code == 409
        assert stale.get('/api/meals').json()['total'] == 0
        assert stale.cookies.get(GUEST_COOKIE) != old_cookie
        assert stale.post('/api/meals', json={'name': '새 체험 기록', 'eaten_at': now()}).status_code == 201
    assert flow.request('POST', '/api/guest-data/import', request) == result
    assert flow.request('GET', '/api/meals')['total'] == 1
    assert flow.session.scalar(select(func.count()).select_from(GuestTransfer).where(GuestTransfer.user_key == 'u:' + user['id'])) == 1


def test_transfer_requires_login_and_signup_never_imports_implicitly(flow):
    saved = meal(flow.client)
    flow.request('POST', '/api/guest-data/import', {}, status=401)
    flow.request('GET', '/api/guest-data', status=401)
    register(flow.client)
    assert flow.request('GET', '/api/meals')['total'] == 0
    assert flow.request('GET', '/api/guest-data')['meals'] == 1
    assert flow.session.get(MealEntry, saved['id']).owner_key.startswith('g:')


def test_mid_transfer_failure_rolls_back_and_retry_succeeds(flow):
    plan, _ = flow.create(CASES[0])
    saved, _ = record(flow.client, plan)
    entry = saved['records'][0]
    feedback = flow.request('PUT', '/api/feedback', {'phase': 'consumed', 'context_id': entry['id'],
        'food_id': entry['food_id'], 'rating': 'like', 'reason': 'taste'})
    guest_owner = flow.session.get(MealPlan, plan['id']).owner_key
    register(flow.client)
    request = {'client_request_id': str(uuid4())}
    connection = flow.session.connection()
    triggered = []

    def fail_feedback_update(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith('UPDATE app.menu_feedback'):
            triggered.append(True)
            raise OperationalError('injected private query', {}, Exception('injected private connection detail'))

    def request_session():
        with Session(bind=connection, join_transaction_mode='create_savepoint') as session:
            yield session

    app.dependency_overrides[get_session] = request_session
    event.listen(connection, 'before_cursor_execute', fail_feedback_update)
    try:
        failed = flow.client.post('/api/guest-data/import', json=request)
        assert failed.status_code == 503 and 'private' not in failed.text
    finally:
        event.remove(connection, 'before_cursor_execute', fail_feedback_update)
        app.dependency_overrides[get_session] = lambda: flow.session
    assert triggered
    flow.session.expire_all()
    assert flow.session.get(MealPlan, plan['id']).owner_key == guest_owner
    assert flow.session.get(MealEntry, entry['id']).owner_key == guest_owner
    assert flow.session.get(MenuFeedback, feedback['id']).owner_key == guest_owner
    assert flow.session.scalar(select(func.count()).select_from(GuestTransfer)) == 0
    result = flow.request('POST', '/api/guest-data/import', request)
    assert result['plans'] == 1 and result['meals'] == len(saved['records'])


def test_invalid_record_inputs_do_not_mutate_plan_or_create_entries(flow):
    plan, _ = flow.create(CASES[0])
    original = deepcopy(plan)
    for changes in [{'eaten_at': (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()},
                    {'amounts': {'foreign-item': '100'}}, {'amounts': {plan['meals'][0]['items'][0]['item_id']: None}}]:
        flow.request('POST', f"/api/plans/{plan['id']}/meals/breakfast/record", {
            'expected_version': plan['version'], 'eaten_at': now(), **changes}, status=422)
    assert flow.request('GET', '/api/plans/' + plan['id']) == original
    assert flow.request('GET', '/api/meals')['total'] == 0
