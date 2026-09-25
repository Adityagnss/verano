"""
Alembic environment.

Imports every module's `models.py` so the shared metadata contains every table, then runs
migrations over the async engine configured by `VERANO_DATABASE_URL` (or the URL passed
in by tests). Migrations are never edited after merge; fix forward with a new one.
"""

import asyncio

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.core.database import Base, load_all_models

load_all_models()

target_metadata = Base.metadata


def database_url() -> str:
    return context.config.attributes.get("database_url") or get_settings().database_url


def run_with(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_online() -> None:
    engine = create_async_engine(database_url())
    async with engine.connect() as connection:
        await connection.run_sync(run_with)
    await engine.dispose()


if context.is_offline_mode():
    context.configure(url=database_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(run_online())
