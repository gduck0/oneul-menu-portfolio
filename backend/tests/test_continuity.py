from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.security import GUEST_COOKIE
from app.personal_models import MealChange, MealEntry
from app.planner_models import MealPlan
from app.personal_ranking import rating_scores
from test_planner import planner_client, create, change
from test_food_api import catalog_client


def record(client, plan, amounts=None):
    meal = plan['meals'][0]
    body = {'client_record_id': str(uuid4()), 'expected_version': plan['version'], 'eaten_at': datetime.now(timezone.utc).isoformat(), 'amounts': amounts or {}}
    response = client.post(f"/api/plans/{plan['id']}/meals/{meal['key']}/record", json=body)
    assert response.status_code == 200, response.text
    return response.json(), body


def action(client, meal, name):
    body = {'expected_version': meal['version'], 'client_request_id': str(uuid4())}
    response = client.post(f"/api/meals/{meal['id']}/{name}", json=body)
    assert response.status_code == 200, response.text
    return response.json(), body


def test_actual_amount_confirmation_and_retry(planner_client):
    client, _ = planner_client
    plan, _ = create(client)
    meal = plan['meals'][0]
    result, body = record(client, plan, {meal['items'][0]['item_id']: '200'})
    assert result['records'][0]['portion']['amount'] == '200'
    assert result['plan']['meals'][0]['items'] == meal['items']
    assert client.post(f"/api/plans/{plan['id']}/meals/{meal['key']}/record", json=body).json() == result
    assert client.post(f"/api/plans/{plan['id']}/meals/{meal['key']}/record", json={**body, 'amounts': {'foreign': '200'}}).status_code == 409


def test_meal_edit_versions_reference_and_history(planner_client):
    client, session = planner_client
    plan, _ = create(client)
    result, _ = record(client, plan)
    meal = result['records'][0]
    original = deepcopy(meal)
    body = {'client_request_id': str(uuid4()), 'expected_version': 1, 'portion': {'amount': '201', 'unit': 'g'}, 'eaten_at': meal['eaten_at'], 'notes': '실제 먹은 양 수정'}
    response = client.patch('/api/meals/' + meal['id'], json=body)
    assert response.status_code == 200, response.text
    saved = response.json()['meal']
    assert saved['version'] == 2 and saved['portion']['amount'] == '201'
    assert client.patch('/api/meals/' + meal['id'], json=body).json() == response.json()
    assert client.patch('/api/meals/' + meal['id'], json={**body, 'client_request_id': str(uuid4())}).status_code == 409
    returned = client.patch('/api/meals/' + meal['id'], json={**body, 'client_request_id': str(uuid4()), 'expected_version': 2, 'portion': original['portion']})
    assert returned.status_code == 200, returned.text
    assert returned.json()['meal']['nutrients'] == original['nutrients']
    assert session.scalar(select(MealChange).where(MealChange.meal_id == meal['id'])).before[0]['portion'] == original['portion']
    assert len(client.get('/api/meals/' + meal['id'] + '/changes').json()) == 2
    assert next(value for value in client.get('/api/meals').json()['items'] if value['id'] == meal['id'])['version'] == 3


def test_cancel_restore_plan_group_and_feedback(planner_client):
    client, session = planner_client
    plan, _ = create(client)
    result, _ = record(client, plan)
    meal = result['records'][0]
    feedback = client.put('/api/feedback', json={'phase': 'consumed', 'context_id': meal['id'], 'food_id': meal['food_id'], 'rating': 'like', 'reason': 'taste'})
    assert feedback.status_code == 200
    owner = session.get(MealEntry, meal['id']).owner_key
    assert rating_scores(session, owner)
    cancelled, body = action(client, meal, 'cancel')
    assert not cancelled['plan']['meals'][0]['consumed']
    assert client.get('/api/meals').json()['total'] == 0
    assert client.get('/api/meals?cancelled=true').json()['total'] == len(result['records'])
    assert not rating_scores(session, owner)
    assert client.post('/api/meals/' + meal['id'] + '/cancel', json=body).json() == cancelled
    assert client.put('/api/feedback', json={'phase': 'consumed', 'context_id': meal['id'], 'food_id': meal['food_id'], 'rating': 'like'}).status_code == 404
    restored, _ = action(client, cancelled['meals'][0], 'restore')
    assert restored['plan']['meals'][0]['consumed']
    assert client.get('/api/meals').json()['total'] == len(result['records'])
    assert rating_scores(session, owner)


def test_restore_cannot_overwrite_changed_plan(planner_client):
    client, _ = planner_client
    plan, _ = create(client)
    result, _ = record(client, plan)
    cancelled, _ = action(client, result['records'][0], 'cancel')
    plan = cancelled['plan']
    plan, _ = change(client, plan, 'breakfast', 'set', custom_name='바꾼 아침', amount_g='250')
    meal = cancelled['meals'][0]
    assert client.post('/api/meals/' + meal['id'] + '/restore', json={'expected_version': meal['version']}).status_code == 409
    assert client.get('/api/plans/' + plan['id']).json()['meals'][0]['items'][0]['name'] == '바꾼 아침'


def test_foreign_owner_cannot_edit_or_cancel(planner_client):
    client, _ = planner_client
    plan, _ = create(client)
    result, _ = record(client, plan)
    meal = result['records'][0]
    with TestClient(app) as other:
        assert other.post('/api/meals/' + meal['id'] + '/cancel', json={'expected_version': 1}).status_code == 404
        assert other.get('/api/meals/' + meal['id'] + '/changes').status_code == 404


def test_plan_history_pagination_date_and_composition(planner_client):
    client, _ = planner_client
    plan, _ = create(client)
    original = deepcopy(plan['meals'][0]['items'])
    plan, _ = change(client, plan, 'breakfast', 'add', custom_name='내 반찬', amount_g='50')
    assert plan['meals'][0]['items'][:-1] == original
    added = plan['meals'][0]['items'][-1]
    plan, _ = change(client, plan, 'breakfast', 'update_item', item_id=added['item_id'], custom_name='바꾼 반찬', amount_g='70')
    plan, _ = change(client, plan, 'breakfast', 'remove', item_id=plan['meals'][0]['items'][-1]['item_id'])
    assert plan['meals'][0]['items'] == original
    past = date.today() - timedelta(days=3)
    for _ in range(11):
        create(client, plan_date=past.isoformat())
    page = client.get('/api/plan-history?limit=10').json()
    assert page['total'] == 12 and len(page['items']) == 10
    assert len(client.get('/api/plan-history?limit=10&offset=10').json()['items']) == 2
    assert client.get('/api/plan-history?date=' + past.isoformat()).json()['total'] == 11


def test_guest_import_preserves_account_preferences_and_retry(planner_client):
    client, _ = planner_client
    plan, _ = create(client)
    result, _ = record(client, plan)
    client.put('/api/preferences', json={'favorite_foods': ['김밥']})
    # Prepare an account with its own settings, then sign in using the guest browser.
    username = 'review_' + uuid4().hex[:12]
    credentials = {'username': username, 'password': 'test-only-password-453'}
    with TestClient(app) as account:
        assert account.post('/api/auth/register', json=credentials).status_code == 201
        account.put('/api/preferences', json={'favorite_foods': ['두부']})
    assert client.post('/api/auth/login', json=credentials).status_code == 200
    summary = client.get('/api/guest-data').json()
    assert summary['plans'] == 1 and summary['meals'] == len(result['records'])
    body = {'client_request_id': str(uuid4()), 'include_settings': True}
    imported = client.post('/api/guest-data/import', json=body)
    assert imported.status_code == 200, imported.text
    assert imported.json()['settings_kept']
    assert client.get('/api/preferences').json()['favorite_foods'] == ['두부']
    assert client.get('/api/plans/' + plan['id']).status_code == 200
    assert client.post('/api/guest-data/import', json=body).json() == imported.json()
    assert client.get('/api/guest-data').json()['plans'] == 0
    assert client.get('/api/meals').json()['total'] == len(result['records'])
    client.post('/api/auth/logout', json={})
    assert client.get('/api/plans').json() == []


def test_custom_record_stays_unknown_and_unit_protected(planner_client):
    client, _ = planner_client
    body = {'name': '직접 만든 저녁', 'portion': {'amount': '200', 'unit': 'g'}, 'eaten_at': datetime.now(timezone.utc).isoformat()}
    meal = client.post('/api/meals', json=body).json()
    edit = {'expected_version': 1, 'portion': {'amount': '300', 'unit': 'g'}, 'eaten_at': meal['eaten_at']}
    response = client.patch('/api/meals/' + meal['id'], json=edit)
    assert response.status_code == 200, response.text
    assert all(value is None for value in response.json()['meal']['nutrients'].values())
    assert client.patch('/api/meals/' + meal['id'], json={**edit, 'expected_version': 2, 'portion': {'amount': '300', 'unit': 'mL'}}).status_code == 422


def test_legacy_plan_record_cancel_restore(planner_client):
    client, session = planner_client
    plan, _ = create(client)
    result, _ = record(client, plan)
    for entry in result['records']:
        row = session.get(MealEntry, entry['id'])
        row.payload = {key: value for key, value in row.payload.items() if key not in ('plan_id', 'meal_key', 'version', 'cancelled_at')}
    session.flush()
    cancelled, _ = action(client, result['records'][0], 'cancel')
    assert cancelled['plan']['id'] == plan['id']
    restored, _ = action(client, cancelled['meals'][0], 'restore')
    assert restored['plan']['meals'][0]['consumed']


def test_import_request_collision_keeps_both_owners_data(planner_client):
    client, session = planner_client
    guest_plan, guest_request = create(client)
    guest_owner = session.get(MealPlan, guest_plan['id']).owner_key
    credentials = {'username': 'collision_' + uuid4().hex[:10], 'password': 'test-only-password-453'}
    with TestClient(app) as account:
        assert account.post('/api/auth/register', json=credentials).status_code == 201
        account_plan = account.post('/api/plans', json=guest_request).json()
    client.post('/api/auth/login', json=credentials)
    response = client.post('/api/guest-data/import', json={})
    assert response.status_code == 409, response.text
    assert session.get(MealPlan, guest_plan['id']).owner_key == guest_owner
    assert client.get('/api/plans/' + account_plan['id']).status_code == 200


def test_default_settings_and_old_guest_refresh(planner_client):
    client, _ = planner_client
    settings = {'energy_target': '2100', 'meal_count': 2, 'default_constraints': {'dinner': {'max_minutes': 20}}, 'favorite_foods': ['두부']}
    assert client.put('/api/preferences', json=settings).status_code == 200
    assert client.get('/api/preferences').json()['default_constraints']['dinner']['max_minutes'] == 20
    credentials = {'username': 'transfer_' + uuid4().hex[:10], 'password': 'test-only-password-453'}
    old_cookie = client.cookies.get(GUEST_COOKIE)
    client.post('/api/auth/register', json=credentials)
    body = {'client_request_id': str(uuid4())}
    response = client.post('/api/guest-data/import', json=body)
    assert response.status_code == 200 and response.json()['settings_imported']
    client.cookies.set(GUEST_COOKIE, old_cookie, domain='testserver.local', path='/')
    assert client.post('/api/guest-data/import', json=body).status_code == 200
    assert client.cookies.get(GUEST_COOKIE) != old_cookie


def test_remove_last_item_does_not_leave_locked_empty_meal(planner_client):
    client, _ = planner_client
    plan, _ = create(client)
    plan, _ = change(client, plan, 'breakfast', 'set', custom_name='내 아침', amount_g='200')
    item = plan['meals'][0]['items'][0]
    plan, _ = change(client, plan, 'breakfast', 'remove', item_id=item['item_id'])
    assert not plan['meals'][0]['items'] and not plan['meals'][0]['locked']
    plan, _ = change(client, plan, 'breakfast', 'replace')
    assert plan['meals'][0]['items']
    response = client.patch('/api/plans/' + plan['id'], json={'meal_key': 'breakfast', 'action': 'add', 'expected_version': plan['version'], 'custom_name': '양 없는 음식'})
    assert response.status_code == 200
    added = response.json()['meals'][0]['items'][-1]
    assert added['amount_g'] is None and all(value is None for value in added['nutrients'].values())
