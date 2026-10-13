from functools import lru_cache

from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase

from app.settings import get_settings
from app.runtime import configure_libpq

configure_libpq()


class Base(DeclarativeBase):
    metadata = MetaData(schema='app')


@lru_cache
def get_engine():
    return create_engine(
        get_settings().database_url.get_secret_value(),
        pool_pre_ping=True,
        connect_args={'connect_timeout': 3},
        hide_parameters=True,
    )
