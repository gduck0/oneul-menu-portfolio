from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select

from app.personal_models import MealEntry
from app.planner_models import MealPlan, PlanOperation
from test_planner import planner_client, create, change
from test_continuity import action
from test_food_api import catalog_client


def three_items(client):
    plan, _ = create(client)
    for index in range(3):
        plan, _ = change(client, plan, 'breakfast', 'set' if index == 0 else 'add',
                         custom_name=f'음식 {index + 1}', amount_g='100')
    return plan


def record(client, plan, **changes):
    body = {'client_record_id': str(uuid4()), 'expected_version': plan['version'],
            'eaten_at': datetime.now(timezone.utc).isoformat(), **changes}
    return client.post(f"/api/plans/{plan['id']}/meals/breakfast/record", json=body), body


def test_skip_food_preserves_plan_and_retry(planner_client):
    client, _ = planner_client
    plan = three_items(client)
    original = deepcopy(plan['meals'][0]['items'])
    response, body = record(client, plan, amounts={original[0]['item_id']: '80'},
                            skipped_item_ids=[original[2]['item_id']])
    assert response.status_code == 200, response.text
    result = response.json()
    assert [entry['name'] for entry in result['records']] == ['음식 1', '음식 2']
    assert [entry['portion']['amount'] for entry in result['records']] == ['80', '100']
    assert result['plan']['meals'][0]['items'] == original
    assert result['plan']['nutrients'] == plan['nutrients']
    assert result['records'][0]['skipped_foods'] == ['음식 3']
    assert client.post(f"/api/plans/{plan['id']}/meals/breakfast/record", json=body).json() == result
    assert client.get('/api/meals').json()['total'] == 2
    altered = {**body, 'skipped_item_ids': []}
    assert client.post(f"/api/plans/{plan['id']}/meals/breakfast/record", json=altered).status_code == 409


def test_invalid_skips_do_not_create_entries_or_change_plan(planner_client):
    client, session = planner_client
    plan = three_items(client)
    ids = [item['item_id'] for item in plan['meals'][0]['items']]
    for fields in [{'skipped_item_ids': ids}, {'skipped_item_ids': ['foreign']},
                   {'skipped_item_ids': [ids[0], ids[0]]},
                   {'skipped_item_ids': [ids[0]], 'amounts': {ids[0]: '50'}},
                   {'amounts': {ids[0]: '0'}}]:
        response, _ = record(client, plan, **fields)
        assert response.status_code == 422, response.text
    assert client.get('/api/meals').json()['total'] == 0
    assert session.get(MealPlan, plan['id']).version == plan['version']


def test_group_pagination_keeps_whole_meal_and_cancel_restore(planner_client):
    client, _ = planner_client
    plan = three_items(client)
    skipped = plan['meals'][0]['items'][2]['item_id']
    response, _ = record(client, plan, skipped_item_ids=[skipped])
    result = response.json()
    solo = client.post('/api/meals', json={'name': '직접 기록', 'portion': {'amount': '150', 'unit': 'g'},
        'eaten_at': datetime.now(timezone.utc).isoformat()})
    assert solo.status_code == 201
    groups = client.get('/api/meal-groups?limit=1').json()
    assert groups['total'] == 2 and groups['total_entries'] == 3
    pages = [groups['items'][0], client.get('/api/meal-groups?limit=1&offset=1').json()['items'][0]]
    linked = next(group for group in pages if group['plan_id'])
    assert len(linked['items']) == 2 and linked['skipped_foods'] == ['음식 3']
    assert linked['label'] == '아침' and linked['nutrients']['energy_kcal'] is None
    cancelled, _ = action(client, result['records'][0], 'cancel')
    assert len(client.get('/api/meal-groups?cancelled=true').json()['items'][0]['items']) == 2
    restored, _ = action(client, cancelled['meals'][0], 'restore')
    assert len(restored['meals']) == 2 and restored['plan']['meals'][0]['skipped_items'][0]['name'] == '음식 3'


def test_legacy_groups_inferred_without_rewriting_records(planner_client):
    client, session = planner_client
    plan = three_items(client)
    result = record(client, plan)[0].json()
    before = {}
    for entry in result['records']:
        row = session.get(MealEntry, entry['id'])
        row.payload = {key: value for key, value in row.payload.items()
                       if key not in ('plan_id', 'meal_key', 'record_group_id', 'skipped_foods')}
        before[row.id] = deepcopy(row.payload)
    session.flush()
    groups = client.get('/api/meal-groups?limit=1').json()
    assert groups['total'] == 1 and len(groups['items'][0]['items']) == 3
    assert groups['items'][0]['meal_key'] == 'breakfast'
    assert all(session.get(MealEntry, entry_id).payload == payload for entry_id, payload in before.items())


def test_cancelled_batches_for_same_plan_are_not_merged(planner_client):
    client, _ = planner_client
    plan = three_items(client)
    first = record(client, plan)[0].json()
    cancelled, _ = action(client, first['records'][0], 'cancel')
    second = record(client, cancelled['plan'])[0].json()
    action(client, second['records'][0], 'cancel')
    groups = client.get('/api/meal-groups?cancelled=true').json()
    assert groups['total'] == 2 and [len(group['items']) for group in groups['items']] == [3, 3]


def test_role_filter_and_group_owner_isolation(planner_client):
    from fastapi.testclient import TestClient
    from app.main import app
    client, _ = planner_client
    plan = three_items(client)
    record(client, plan)
    for role in ('staple', 'protein', 'soup', 'main'):
        result = client.get('/api/planner/menus', params={'role': role, 'limit': 1}).json()
        assert result['total'] > 0 and all(item['role'] == role for item in result['items'])
        last = client.get('/api/planner/menus', params={'role': role, 'limit': 1, 'offset': result['total'] - 1}).json()
        assert len(last['items']) == 1 and last['items'][0]['role'] == role
    with TestClient(app) as other:
        assert other.get('/api/meal-groups').json()['total'] == 0
