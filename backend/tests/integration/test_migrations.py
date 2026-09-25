"""
Migration check: on a fresh, separate database, the migrations upgrade to head, match the
models exactly (`alembic check`), downgrade to an empty schema and upgrade again. This is
what makes "every migration is reversible and nothing is missing" a gate, not a hope.
"""

import asyncio
import uuid
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import Settings
from tests.helpers import ROOT

pytestmark = pytest.mark.integration


async def _run(url: str, statement: str) -> list[object]:
    engine = create_async_engine(url, isolation_level="AUTOCOMMIT")
    async with engine.connect() as connection:
        result = await connection.execute(text(statement))
        rows: list[object] = list(result.scalars().all()) if result.returns_rows else []
    await engine.dispose()
    return rows


@pytest.fixture
def scratch_database(settings: Settings) -> Iterator[str]:
    name = f"verano_migrations_{uuid.uuid4().hex[:8]}"
    asyncio.run(_run(settings.database_url, f'CREATE DATABASE "{name}"'))
    yield make_url(settings.database_url).set(database=name).render_as_string(hide_password=False)
    asyncio.run(_run(settings.database_url, f'DROP DATABASE "{name}" WITH (FORCE)'))


def alembic(url: str) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.attributes["database_url"] = url
    return config


def tables(url: str) -> list[object]:
    return asyncio.run(_run(url, "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"))


def test_migrations_match_the_models_and_downgrade_to_an_empty_schema(scratch_database: str) -> None:
    config = alembic(scratch_database)
    command.upgrade(config, "head")
    command.check(config)
    assert len(tables(scratch_database)) > 1
    command.downgrade(config, "base")
    assert tables(scratch_database) == ["alembic_version"]
    command.upgrade(config, "head")
