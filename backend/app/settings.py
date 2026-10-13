from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

from app.runtime import database_port

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / '.env', extra='ignore', hide_input_in_errors=True)
    app_env: Literal['development', 'test'] = 'development'
    database_url: SecretStr

    @model_validator(mode='after')
    def validate_database_target(self):
        url = make_url(self.database_url.get_secret_value())
        expected = ('oneul_menu_test', 'oneul_test') if self.app_env == 'test' else ('oneul_menu_dev', 'oneul_dev')
        if url.drivername != 'postgresql+psycopg' or (url.database, url.username) != expected:
            raise ValueError('실행 모드와 DB 이름·계정이 일치해야 합니다.')
        if url.host != '127.0.0.1' or url.port != database_port():
            raise ValueError('이 체크아웃의 전용 로컬 DB만 사용합니다.')
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
