"""The judge cache (ADR 0021): scoring the same answers again reuses the stored results and makes no new judge call."""

import httpx
import pytest
from sqlalchemy import func, select

from app.core.container import Container
from app.core.jobs import InlineJobQueue
from app.modules.evaluation.models import JudgeCacheEntry
from app.modules.gateway.models import LLMCall
from app.modules.gateway.schemas import CallPurpose
from tests.helpers import Session, base, judged_project, run_good

pytestmark = [pytest.mark.integration]


async def judge_calls(container: Container) -> int:
    async with container.database.sessions() as db:
        query = select(func.count()).select_from(LLMCall).where(LLMCall.purpose == CallPurpose.JUDGE)
        return int(await db.scalar(query) or 0)


async def cached(container: Container) -> int:
    async with container.database.sessions() as db:
        return int(await db.scalar(select(func.count()).select_from(JudgeCacheEntry)) or 0)


async def test_scoring_the_same_answers_again_makes_no_new_judge_call(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, container: Container
) -> None:
    models = await judged_project(client, session, jobs, set_judge="scripted")
    experiment = await run_good(client, session, jobs, models)
    first_calls, stored = await judge_calls(container), await cached(container)
    assert first_calls > 0
    assert stored > 0

    again = await client.post(
        f"{base(session)}/experiments/{experiment['id']}/rescore", json={}, headers=session.headers
    )
    assert again.status_code == 202, again.text
    await jobs.drain()
    assert await judge_calls(container) == first_calls  # every judged result came from the cache

    results = (
        await client.get(f"{base(session)}/experiments/{experiment['id']}/results", headers=session.headers)
    ).json()
    assert [r["trigger"] for r in results["evaluation_runs"]] == ["rescore", "initial"]
    cases = (await client.get(f"{base(session)}/experiments/{experiment['id']}/cases", headers=session.headers)).json()
    assert all(o["judged"] for case in cases for o in case["outputs"])
