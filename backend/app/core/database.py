"""
Database engine, declarative base and session dependency.

One async engine and session factory per process, owned by a `Database` object that the
app lifespan (or a worker) creates and disposes. Tables across all modules share one
`Base` with a constraint naming convention so Alembic migrations are deterministic.
Request handlers receive an `AsyncSession` through `SessionDep`; the session commits when
the handler returns normally and rolls back on any exception. `load_all_models` imports
every module's tables; `Database` calls it, so every process (API, worker, Alembic, tests)
knows every table a foreign key can point to.
"""

import importlib
import pkgutil
import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any

from fastapi import Depends, Request
from sqlalchemy import DateTime, Enum, MetaData, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.config import Settings
from app.core.ids import uuid7

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {dict[str, Any]: JSONB, list[Any]: JSONB, datetime: DateTime(timezone=True)}


def str_enum(enum_cls: type[StrEnum], name: str) -> Enum:
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=32,
        values_callable=lambda e: [m.value for m in e],
    )


class IdMixin:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


def load_all_models() -> None:
    import app.modules

    for module in pkgutil.iter_modules(app.modules.__path__):
        if importlib.util.find_spec(f"app.modules.{module.name}.models"):
            importlib.import_module(f"app.modules.{module.name}.models")


class Database:
    def __init__(self, settings: Settings) -> None:
        load_all_models()
        self.engine: AsyncEngine = create_async_engine(
            settings.database_url,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_pre_ping=True,
        )
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def dispose(self) -> None:
        await self.engine.dispose()


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    database: Database = request.app.state.container.database
    async with database.sessions() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise


SessionDep = Annotated[AsyncSession, Depends(get_session)]
