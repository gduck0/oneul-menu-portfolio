from pathlib import Path

from dotenv import dotenv_values
import pytest
from sqlalchemy import create_engine

from app.settings import Settings


@pytest.fixture(scope='session')
def test_engine():
    test_file = Path(__file__).resolve().parents[2] / '.env.test'
    url = dotenv_values(test_file).get('TEST_DATABASE_URL')
    if not url:
        raise RuntimeError('명시적인 테스트 DB 설정이 필요합니다. 개발 DB로 대체하지 않습니다.')
    settings = Settings(app_env='test', database_url=url, _env_file=None)
    engine = create_engine(settings.database_url.get_secret_value(), connect_args={'connect_timeout': 3}, hide_parameters=True)
    yield engine
    engine.dispose()
