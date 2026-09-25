"""
Shared test fixtures.

Integration tests run against real Postgres 16 and Valkey 8: containers started once per
session by Testcontainers, or the services named by VERANO_TEST_DATABASE_URL and
VERANO_TEST_VALKEY_URL (CI runs them as service containers). Either way the database is
migrated with the real Alembic migrations. Before every integration test the tables are
truncated, Valkey is flushed and a fresh mock provider is installed, so tests are
independent and deterministic. Unit tests never request these
fixtures and therefore never start a container. No test touches the network: providers
are replayed with respx and every LLM call goes to the mock provider.
"""

import os
import uuid
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass

import httpx
import litellm
import pytest
from alembic import command
from alembic.config import Config
from cryptography.fernet import Fernet
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy import text
from testcontainers.community.postgres import PostgresContainer
from testcontainers.community.redis import RedisContainer

from app.core.config import Settings
from app.core.container import Container
from app.core.database import Base, load_all_models
from app.main import create_app
from app.modules.gateway.plugins.mock_provider import install_mock_provider
from tests.helpers import FIXTURES, ROOT, Session, compose_image, sign_up


@dataclass(frozen=True)
class Infra:
    database_url: str
    valkey_url: str


@pytest.fixture(scope="session")
def infra() -> Iterator[Infra]:
    provided = os.environ.get("VERANO_TEST_DATABASE_URL"), os.environ.get("VERANO_TEST_VALKEY_URL")
    if all(provided):
        yield Infra(database_url=str(provided[0]), valkey_url=str(provided[1]))
        return
    with (
        PostgresContainer(compose_image("postgres"), driver="asyncpg") as postgres,
        RedisContainer(compose_image("valkey")) as valkey,
    ):
        valkey_url = f"redis://{valkey.get_container_host_ip()}:{valkey.get_exposed_port(6379)}/0"
        yield Infra(database_url=postgres.get_connection_url(), valkey_url=valkey_url)


@pytest.fixture(scope="session")
def settings(infra: Infra) -> Settings:
    return Settings(
        _env_file=None,
        database_url=infra.database_url,
        valkey_url=infra.valkey_url,
        master_keys=SecretStr(Fernet.generate_key().decode()),
        jwt_secret=SecretStr("test-only-jwt-secret-with-enough-entropy-0123456789"),
        mock_provider_enabled=True,
        mock_models_path=FIXTURES / "mock_models.yaml",
        mock_scripted_dir=FIXTURES / "scripted/responses",
        mock_answer_key_path=FIXTURES / "scripted/answer_key.yaml",
        ollama_base_url="http://ollama.test:11434",
        auth_rate_limit_per_ip=10,
        auth_rate_limit_per_email=4,
    )


@pytest.fixture(scope="session")
def migrated(settings: Settings) -> None:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.attributes["database_url"] = settings.database_url
    command.upgrade(config, "head")


@pytest.fixture(scope="session")
async def app(settings: Settings, migrated: None) -> AsyncIterator[FastAPI]:
    litellm.disable_aiohttp_transport = True
    application = create_app(settings)
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
def container(app: FastAPI) -> Container:
    built: Container = app.state.container
    return built


@pytest.fixture
async def clean(container: Container, settings: Settings) -> None:
    load_all_models()
    tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
    async with container.database.engine.begin() as connection:
        await connection.execute(text(f"TRUNCATE {tables} CASCADE"))
    await container.valkey.flushall()
    install_mock_provider(settings)


@pytest.fixture
async def client(app: FastAPI, clean: None) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://verano.test") as http:
        yield http


@pytest.fixture
async def session(client: httpx.AsyncClient) -> Session:
    headers = await sign_up(client, f"owner-{uuid.uuid4().hex[:8]}@example.com")
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()
    project = await client.post("/api/v1/projects", json={"name": "Support triage"}, headers=headers)
    assert project.status_code == 201, project.text
    return Session(headers=headers, user_id=uuid.UUID(me["user"]["id"]), project_id=uuid.UUID(project.json()["id"]))
