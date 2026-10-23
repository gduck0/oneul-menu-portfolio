from datetime import timedelta
import json
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.database import get_engine
from app.main import app
from app.personal_models import GuestTransfer, PersonalSettings
from app.record_models import AuthSession, User
from app.runtime import application_origins
from app.security import GUEST_COOKIE, SESSION_COOKIE, login_attempts, token_hash, utcnow
from app.session_dependency import get_session

PASSWORD = 'local-test-password-2026'


@pytest.fixture
def account_client(test_engine):
    with test_engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection, join_transaction_mode='create_savepoint') as session:
            app.dependency_overrides[get_session] = lambda: session
            login_attempts.attempts.clear()
            try:
                with TestClient(app) as client:
                    yield client, session
            finally:
                app.dependency_overrides.clear()
                login_attempts.attempts.clear()
        transaction.rollback()


def register(client, username=None):
    username = username or 'user_' + uuid4().hex[:16]
    response = client.post('/api/auth/register', json={'username': username, 'password': PASSWORD})
    assert response.status_code == 201, response.text
    return response.json()['user']


def test_registration_session_and_logout(account_client):
    client, session = account_client
    user = register(client)
    cookie = client.cookies.get(SESSION_COOKIE)
    stored = session.get(User, user['id'])
    assert PASSWORD not in stored.password_hash
    assert stored.password_hash.startswith('scrypt$131072$8$1$')
    entry = session.get(AuthSession, token_hash(cookie))
    assert entry.user_id == user['id'] and entry.token_hash != cookie
    assert client.get('/api/auth/me').json() == {'user': user}
    assert client.post('/api/auth/logout', json={}).status_code == 204
    assert session.get(AuthSession, token_hash(cookie)) is None
    assert client.get('/api/auth/me').json()['user'] is None
    assert client.post('/api/auth/logout', json={}).status_code == 204


def test_duplicate_normalization_does_not_create_account(account_client):
    client, session = account_client
    username = 'Case_' + uuid4().hex[:12]
    user = register(client, username)
    assert user['username'] == username.casefold()
    response = client.post('/api/auth/register', json={'username': username.upper(), 'password': PASSWORD})
    assert response.status_code == 409
    assert session.scalar(select(func.count()).select_from(User).where(User.username == username.casefold())) == 1


def test_login_rotation_expiration_and_failure_limit(account_client):
    client, session = account_client
    user = register(client)
    original_cookie = client.cookies.get(SESSION_COOKIE)
    payload = {'username': user['username'], 'password': PASSWORD}
    response = client.post('/api/auth/login', json=payload)
    assert response.status_code == 200
    assert 'HttpOnly' in response.headers['set-cookie'] and 'SameSite=lax' in response.headers['set-cookie']
    assert client.cookies.get(SESSION_COOKIE) != original_cookie
    assert session.get(AuthSession, token_hash(original_cookie)) is None
    entry = session.get(AuthSession, token_hash(client.cookies.get(SESSION_COOKIE)))
    entry.expires_at = utcnow() - timedelta(seconds=1)
    session.flush()
    assert client.get('/api/auth/me').json()['user'] is None
    for _ in range(5):
        response = client.post('/api/auth/login', json={**payload, 'password': 'wrong-password-2026'})
        assert response.status_code == 401 and PASSWORD not in response.text
    limited = client.post('/api/auth/login', json=payload)
    assert limited.status_code == 429 and limited.headers['retry-after'] == '60'


def test_guest_settings_survive_reconnection_and_are_separate(account_client):
    client, session = account_client
    assert client.get('/api/preferences').json()['energy_target'] is None
    response = client.put('/api/preferences', json={'goal': 'protein', 'favorite_foods': [' 김밥 ', '김밥', ''], 'frequent_foods': ['집밥']})
    assert response.status_code == 200
    assert response.json()['favorite_foods'] == ['김밥']
    guest_cookie = client.cookies.get(GUEST_COOKIE)
    with TestClient(app) as reopened:
        reopened.cookies.update(client.cookies)
        assert reopened.get('/api/preferences').json() == response.json()
    with TestClient(app) as other:
        assert other.get('/api/preferences').json()['goal'] == 'balanced'
        assert other.cookies.get(GUEST_COOKIE) != guest_cookie
    assert session.get(PersonalSettings, 'g:' + token_hash(guest_cookie)) is not None


def test_account_settings_relogin_and_guest_are_not_automatically_merged(account_client):
    client, _ = account_client
    assert client.put('/api/preferences', json={'favorite_foods': ['비빔밥']}).status_code == 200
    guest_cookie = client.cookies.get(GUEST_COOKIE)
    user = register(client)
    assert client.get('/api/preferences').json()['favorite_foods'] == []
    settings = {'goal': 'energy', 'energy_target': '1900', 'meal_count': 4, 'favorite_foods': ['김밥'],
                'avoided_foods': ['생선'], 'default_constraints': {'snack': {'no_cook': True, 'max_minutes': 10, 'avoided_foods': ['견과']}}}
    saved = client.put('/api/preferences', json=settings)
    assert saved.status_code == 200
    assert client.post('/api/auth/logout', json={}).status_code == 204
    assert client.cookies.get(GUEST_COOKIE) == guest_cookie
    assert client.get('/api/preferences').json()['favorite_foods'] == ['비빔밥']
    with TestClient(app) as other:
        other_user = register(other)
        assert other_user['id'] != user['id']
        assert other.get('/api/preferences').json()['favorite_foods'] == []
        assert other.put('/api/preferences', json={'favorite_foods': ['샌드위치']}).status_code == 200
    assert client.post('/api/auth/login', json={'username': user['username'], 'password': PASSWORD}).status_code == 200
    assert client.get('/api/preferences').json() == saved.json()


@pytest.mark.parametrize('invalid', [
    {'energy_target': 599}, {'energy_target': 5001}, {'energy_target': 'NaN'}, {'meal_count': 1},
    {'goal': 'unknown'}, {'favorite_foods': ['김밥'], 'avoided_foods': [' 김밥 ']},
    {'favorite_foods': ['가' * 41]}, {'favorite_foods': [str(i) for i in range(11)]},
    {'default_constraints': {'snack': {'max_minutes': 1}}},
    {'default_constraints': {'dinner': {'tools': ['oven']}}},
    {'default_constraints': {'unknown': {}}}, {'owner_key': 'u:another-user'},
])
def test_invalid_preferences_preserve_previous_settings(account_client, invalid):
    client, _ = account_client
    baseline = client.put('/api/preferences', json={'favorite_foods': ['김밥'], 'energy_target': '1800'}).json()
    response = client.put('/api/preferences', json=invalid)
    assert response.status_code == 422
    assert client.get('/api/preferences').json() == baseline


@pytest.mark.parametrize('invalid', [{'username': 'x', 'password': PASSWORD},
    {'username': 'valid_user', 'password': 'secret!'}, {'username': 'user name', 'password': PASSWORD},
    {'username': 'valid_user', 'password': PASSWORD, 'user_id': 'another'}])
def test_validation_hides_password_and_input(account_client, invalid):
    client, _ = account_client
    response = client.post('/api/auth/register', json=invalid)
    assert response.status_code == 422
    assert invalid['password'] not in response.text
    assert all(set(item) == {'loc', 'msg', 'type'} for item in response.json()['detail'])


def test_origin_content_type_and_cache_headers(account_client):
    client, _ = account_client
    payload = {'favorite_foods': ['김밥']}
    for origin in sorted(application_origins()):
        response = client.put('/api/preferences', json=payload, headers={'Origin': origin})
        assert response.status_code == 200
        assert response.headers['cache-control'] == 'no-store'
        assert response.headers['x-content-type-options'] == 'nosniff'
    before = client.get('/api/preferences').json()
    for headers in [{'Origin': 'https://unrelated.example'}, {'Origin': 'http://127.0.0.1:15178'}, {'Sec-Fetch-Site': 'cross-site'}]:
        assert client.put('/api/preferences', json={}, headers=headers).status_code == 403
    assert client.put('/api/preferences', content='goal=protein', headers={'Content-Type': 'application/x-www-form-urlencoded'}).status_code == 415
    assert client.get('/api/preferences').json() == before


def test_cookie_names_do_not_accept_review_sessions(account_client):
    client, _ = account_client
    register(client)
    token = client.cookies.get(SESSION_COOKIE)
    guest = client.get('/api/preferences')
    assert guest.status_code == 200
    with TestClient(app) as other:
        other.cookies.set('oneul_review_session', token)
        other.cookies.set('oneul_review_guest', client.cookies.get(GUEST_COOKIE))
        assert other.get('/api/auth/me').json()['user'] is None
        assert other.cookies.get(GUEST_COOKIE) != client.cookies.get(GUEST_COOKIE)


def test_transferred_guest_is_rotated_on_read_and_rejected_on_write(account_client):
    client, session = account_client
    client.get('/api/preferences')
    cookie = client.cookies.get(GUEST_COOKIE)
    guest = 'g:' + token_hash(cookie)
    session.add(GuestTransfer(id=str(uuid4()), guest_key=guest, user_key='u:previous-owner',
                             client_request_id=str(uuid4()), input_hash='0' * 64, payload={}, created_at=utcnow()))
    session.flush()
    assert client.put('/api/preferences', json={'goal': 'protein'}).status_code == 409
    assert session.get(PersonalSettings, guest) is None
    assert client.get('/api/preferences').status_code == 200
    assert client.cookies.get(GUEST_COOKIE) != cookie
    assert client.put('/api/preferences', json={'goal': 'protein'}).status_code == 200


def test_database_failure_is_sanitized_for_account_and_settings():
    class UnavailableEngine:
        def connect(self):
            raise OperationalError('private-query', {}, Exception('private-connection-detail'))

    app.dependency_overrides[get_engine] = lambda: UnavailableEngine()
    try:
        with TestClient(app) as client:
            client.cookies.set(SESSION_COOKIE, 'A' * 43)
            for response in [client.get('/api/auth/me'), client.get('/api/preferences'),
                             client.put('/api/preferences', json={'goal': 'protein'})]:
                assert response.status_code == 503
                assert 'private-query' not in response.text and 'private-connection-detail' not in response.text
    finally:
        app.dependency_overrides.clear()


def test_only_current_stage_endpoints_are_exposed():
    paths = set(app.openapi()['paths'])
    assert {'/api/auth/register', '/api/auth/login', '/api/auth/logout', '/api/auth/me', '/api/preferences'} <= paths
    assert not any(path.startswith(('/api/planner', '/api/meals', '/api/feedback', '/api/recommendations', '/api/history', '/api/guest')) for path in paths)


def test_runtime_origins_follow_checkout_configuration(tmp_path):
    runtime = tmp_path / 'runtime.json'
    runtime.write_text(json.dumps({'frontend_port': 16001, 'backend_port': 19001}), encoding='utf-8')
    assert application_origins(runtime) == {'http://127.0.0.1:16001', 'http://localhost:16001', 'http://127.0.0.1:19001', 'http://localhost:19001'}


@pytest.mark.parametrize('ports', [{'frontend_port': True}, {'backend_port': '19000'}, {'frontend_port': 80}, {'backend_port': 70000}, {'frontend_port': 16001, 'backend_port': 16001}])
def test_invalid_origin_ports_fail_closed(tmp_path, ports):
    runtime = tmp_path / 'runtime.json'
    runtime.write_text(json.dumps(ports), encoding='utf-8')
    with pytest.raises(ValueError):
        application_origins(runtime)
