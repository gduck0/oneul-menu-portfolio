import uuid

from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from app.database import get_engine
from app.main import app
from app.settings import Settings


def test_test_mode_rejects_development_database():
    with pytest.raises(ValidationError):
        Settings(app_env='test', database_url='postgresql+psycopg://oneul_dev:example@127.0.0.1:15432/oneul_menu_dev', _env_file=None)


def test_test_mode_rejects_admin_account():
    with pytest.raises(ValidationError):
        Settings(app_env='test', database_url='postgresql+psycopg://oneul_admin:example@127.0.0.1:15432/oneul_menu_test', _env_file=None)


def test_test_mode_rejects_remote_database():
    with pytest.raises(ValidationError):
        Settings(app_env='test', database_url='postgresql+psycopg://oneul_test:example@remote.example:15432/oneul_menu_test', _env_file=None)


def test_postgresql_transaction_commit_and_rollback(test_engine):
    name = 'probe_' + uuid.uuid4().hex
    with test_engine.connect() as connection:
        assert connection.execute(text('SELECT current_database()')).scalar_one() == 'oneul_menu_test'
    try:
        with test_engine.begin() as connection:
            connection.execute(text(f'CREATE TABLE app.{name} (id integer PRIMARY KEY, label text NOT NULL)'))
            connection.execute(text(f'INSERT INTO app.{name} VALUES (1, :label)'), {'label': '한 끼 기록'})
        with test_engine.connect() as connection:
            assert connection.execute(text(f'SELECT label FROM app.{name} WHERE id = 1')).scalar_one() == '한 끼 기록'
            connection.execute(text(f'UPDATE app.{name} SET label = :label WHERE id = 1'), {'label': '취소할 변경'})
            connection.rollback()
            assert connection.execute(text(f'SELECT label FROM app.{name} WHERE id = 1')).scalar_one() == '한 끼 기록'
    finally:
        with test_engine.begin() as connection:
            connection.execute(text(f'DROP TABLE IF EXISTS app.{name}'))


def test_test_account_cannot_connect_to_development_database(test_engine):
    wrong_database = create_engine(test_engine.url.set(database='oneul_menu_dev'), connect_args={'connect_timeout': 3}, hide_parameters=True)
    try:
        with pytest.raises(OperationalError):
            with wrong_database.connect():
                pytest.fail('테스트 계정으로 개발 DB에 연결했습니다.')
    finally:
        wrong_database.dispose()


def test_test_account_has_no_admin_or_cross_database_privileges(test_engine):
    with test_engine.connect() as connection:
        privileges = connection.execute(text('SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication FROM pg_roles WHERE rolname = current_user')).one()
        assert tuple(privileges) == (False, False, False, False)
        assert connection.execute(text("SELECT has_database_privilege(current_user, 'oneul_menu_dev', 'CONNECT')")).scalar_one() is False


def test_ready_checks_real_test_database(test_engine):
    app.dependency_overrides[get_engine] = lambda: test_engine
    try:
        with TestClient(app) as client:
            assert client.get('/api/ready').json() == {'status': 'ok', 'service': 'oneul-menu'}
    finally:
        app.dependency_overrides.clear()


def test_ready_returns_503_without_database_secrets():
    class UnavailableEngine:
        def connect(self):
            raise OperationalError('SELECT 1', {}, Exception('private-connection-detail'))

    app.dependency_overrides[get_engine] = lambda: UnavailableEngine()
    try:
        with TestClient(app) as client:
            response = client.get('/api/ready')
            assert response.status_code == 503
            assert response.json() == {'detail': '서비스 준비 중입니다.'}
            assert 'private-connection-detail' not in response.text
            assert client.get('/api/health').status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_development_mode_rejects_other_checkout_port():
    from app.runtime import database_port
    wrong_port = 15433 if database_port() == 15432 else 15432
    with pytest.raises(ValidationError):
        Settings(app_env='development', database_url=f'postgresql+psycopg://oneul_dev:example@127.0.0.1:{wrong_port}/oneul_menu_dev', _env_file=None)


def test_test_mode_rejects_other_checkout_port():
    from app.runtime import database_port
    wrong_port = 15433 if database_port() == 15432 else 15432
    with pytest.raises(ValidationError):
        Settings(app_env='test', database_url=f'postgresql+psycopg://oneul_test:example@127.0.0.1:{wrong_port}/oneul_menu_test', _env_file=None)


def test_development_account_cannot_connect_to_test_database():
    from dotenv import dotenv_values
    from app.settings import PROJECT_ROOT
    settings = Settings(app_env='development', database_url=dotenv_values(PROJECT_ROOT / '.env')['DATABASE_URL'], _env_file=None)
    engine = create_engine(settings.database_url.get_secret_value(), connect_args={'connect_timeout': 3}, hide_parameters=True)
    wrong_database = create_engine(engine.url.set(database='oneul_menu_test'), connect_args={'connect_timeout': 3}, hide_parameters=True)
    try:
        with engine.connect() as connection:
            assert tuple(connection.execute(text('SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication FROM pg_roles WHERE rolname = current_user')).one()) == (False, False, False, False)
            assert connection.execute(text("SELECT has_database_privilege(current_user, 'oneul_menu_test', 'CONNECT')")).scalar_one() is False
        with pytest.raises(OperationalError):
            with wrong_database.connect():
                pytest.fail('개발 계정으로 테스트 DB에 연결했습니다.')
    finally:
        wrong_database.dispose()
        engine.dispose()


def test_ready_returns_503_before_schema_migration():
    from unittest.mock import MagicMock
    engine = MagicMock()
    engine.connect.return_value.__enter__.return_value.execute.return_value.scalar_one_or_none.return_value = None
    app.dependency_overrides[get_engine] = lambda: engine
    try:
        with TestClient(app) as client:
            assert client.get('/api/ready').status_code == 503
    finally:
        app.dependency_overrides.clear()
