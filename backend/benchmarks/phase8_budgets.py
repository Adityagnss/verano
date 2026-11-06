"""
Phase 8 latency budget (ENGINEERING_STANDARDS section 4b): fetching a prompt by name and label must take under 10 ms
on the server for the app that asks (a cached prompt costs a 304).

Runs the real app in-process (auth, project check, one joined query) against a real Postgres and Valkey: the services
named by VERANO_TEST_DATABASE_URL and VERANO_TEST_VALKEY_URL, or throw-away Testcontainers when they are not set.
Prints the median, 95th percentile and best of many calls for a full answer and for a 304.
"""

import asyncio
import os
import statistics
import time
import uuid

import httpx
from alembic import command
from alembic.config import Config
from cryptography.fernet import Fernet
from pydantic import SecretStr
from testcontainers.community.postgres import PostgresContainer
from testcontainers.community.redis import RedisContainer

from app.core.config import Settings
from app.core.jobs import InlineJobQueue, load_all_jobs
from app.main import create_app
from tests.helpers import ROOT, TEST_CONTAINER_LABELS, compose_image, sign_up

CALLS = 300
BUDGET_MS = 10.0


def settings_for(database_url: str, valkey_url: str) -> Settings:
    return Settings(
        _env_file=None,
        database_url=database_url,
        valkey_url=valkey_url,
        master_keys=SecretStr(Fernet.generate_key().decode()),
        jwt_secret=SecretStr("benchmark-only-jwt-secret-with-enough-entropy-0123456789"),
    )


async def measure(settings: Settings) -> list[tuple[str, float, float, float]]:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.attributes["database_url"] = settings.database_url
    await asyncio.to_thread(command.upgrade, config, "head")
    load_all_jobs()
    jobs = InlineJobQueue()
    app = create_app(settings, jobs=jobs)
    rows: list[tuple[str, float, float, float]] = []
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="https://bench.test") as client,
    ):
        headers = await sign_up(client, f"bench-{uuid.uuid4().hex[:8]}@example.com")
        project = (await client.post("/api/v1/projects", json={"name": "Bench"}, headers=headers)).json()
        root = f"/api/v1/projects/{project['id']}"
        prompt = (
            await client.post(
                f"{root}/prompts", json={"name": "Triage", "user_template": "Ticket: {{ ticket }}"}, headers=headers
            )
        ).json()
        await client.put(
            f"{root}/prompts/{prompt['id']}/labels/production",
            json={"version_id": prompt["latest_version"]["id"]},
            headers=headers,
        )
        url = f"{root}/prompt-by-name/Triage"
        full = await client.get(url, params={"label": "production"}, headers=headers)
        etag = full.headers["etag"]
        for title, extra in (("200 with the prompt", {}), ("304 not modified", {"If-None-Match": etag})):
            times = []
            for _ in range(CALLS + 20):
                began = time.perf_counter()
                await client.get(url, params={"label": "production"}, headers={**headers, **extra})
                times.append((time.perf_counter() - began) * 1000)
            times = sorted(times[20:])
            rows.append((title, statistics.median(times), times[int(len(times) * 0.95)], times[0]))
    return rows


def main() -> None:
    provided = os.environ.get("VERANO_TEST_DATABASE_URL"), os.environ.get("VERANO_TEST_VALKEY_URL")
    if all(provided):
        rows = asyncio.run(measure(settings_for(str(provided[0]), str(provided[1]))))
    else:
        postgres = PostgresContainer(compose_image("postgres"), driver="asyncpg").with_kwargs(
            labels=TEST_CONTAINER_LABELS
        )
        valkey = RedisContainer(compose_image("valkey")).with_kwargs(labels=TEST_CONTAINER_LABELS)
        with postgres, valkey:
            valkey_url = f"redis://{valkey.get_container_host_ip()}:{valkey.get_exposed_port(6379)}/0"
            rows = asyncio.run(measure(settings_for(postgres.get_connection_url(), valkey_url)))
    print(f"Fetch a prompt by name and label (budget {BUDGET_MS:.0f} ms, median of {CALLS} calls, in-process HTTP)")
    for title, median, p95, best in rows:
        verdict = "within budget" if median < BUDGET_MS else "OVER BUDGET"
        print(f"  {title:<22} median {median:6.2f} ms   p95 {p95:6.2f} ms   best {best:6.2f} ms   {verdict}")


if __name__ == "__main__":
    main()
