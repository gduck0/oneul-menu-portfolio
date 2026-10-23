from alembic import context
from sqlalchemy import create_engine, pool

from app.database import Base
from app import food_models, record_models, personal_models, planner_models
from app.settings import get_settings

database_url = get_settings().database_url.get_secret_value()
target_metadata = Base.metadata

if context.is_offline_mode():
    context.configure(url=database_url, target_metadata=target_metadata, literal_binds=True, include_schemas=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(database_url, poolclass=pool.NullPool, connect_args={'connect_timeout': 3}, hide_parameters=True)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, include_schemas=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()
