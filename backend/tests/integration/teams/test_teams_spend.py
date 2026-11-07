"""
S8.13: the workspace spending limit. The Guardrails screen shows spend against the limit, the gateway refuses a
call before making it once the limit is reached, and a running experiment stops with its finished answers kept and
says why.
"""

from decimal import Decimal
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select, text

from app.core.container import Container
from app.core.jobs import InlineJobQueue
from app.modules.gateway.models import LLMCall
from tests.helpers import Session, add_credential, approved_project
from tests.integration.teams.conftest import Team

pytestmark = [pytest.mark.integration, pytest.mark.gateway]


async def call(client: httpx.AsyncClient, session: Session, credential_id: str) -> httpx.Response:
    body = {"credential_id": credential_id, "model": "echo", "messages": [{"role": "user", "content": "hello gateway"}]}
    return await client.post(f"/api/v1/projects/{session.project_id}/llm-calls", json=body, headers=session.headers)


async def guardrails(client: httpx.AsyncClient, team: Team, role: str = "owner") -> dict[str, Any]:
    response = await client.get(f"{team.base}/guardrails", headers=team.h(role))
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def scale_spend_to(container: Container, total: Decimal) -> None:
    """Make what has been spent so far add up to `total` dollars (the mock models are far too cheap to reach a
    limit of one cent any other way)."""
    async with container.database.engine.begin() as connection:
        spent = (await connection.execute(select(func.sum(LLMCall.cost)))).scalar_one()
        assert spent is not None
        await connection.execute(text("UPDATE llm_calls SET cost = cost * :f"), {"f": total / spent})


async def test_the_guardrails_screen_shows_the_limit_and_what_has_been_spent(
    client: httpx.AsyncClient, team: Team, team_session: Session, container: Container
) -> None:
    empty = await guardrails(client, team)
    assert empty["monthly_spend_limit"] is None
    assert Decimal(empty["spent_this_month"]) == 0
    assert empty["percent_used"] is None
    assert empty["limit_reached"] is False

    credential = await add_credential(client, team_session, "mock")
    assert (await call(client, team_session, credential["id"])).status_code == 200
    put = await client.put(f"{team.base}/guardrails", json={"monthly_spend_limit": "10"}, headers=team.headers)
    assert put.status_code == 200
    assert Decimal(put.json()["monthly_spend_limit"]) == 10
    await scale_spend_to(container, Decimal("2.50"))
    shown = await guardrails(client, team, "member")
    assert Decimal(shown["spent_this_month"]) == Decimal("2.5")
    assert shown["percent_used"] == 25.0
    assert shown["limit_reached"] is False

    for bad in ("0", "-5", "abc"):
        refused = await client.put(f"{team.base}/guardrails", json={"monthly_spend_limit": bad}, headers=team.headers)
        assert refused.status_code == 422
    cleared = await client.put(f"{team.base}/guardrails", json={"monthly_spend_limit": None}, headers=team.headers)
    assert cleared.json()["monthly_spend_limit"] is None


async def test_the_gateway_refuses_a_call_before_making_it_once_the_limit_is_reached(
    client: httpx.AsyncClient, team: Team, team_session: Session, container: Container
) -> None:
    credential = await add_credential(client, team_session, "mock")
    assert (await call(client, team_session, credential["id"])).status_code == 200
    await client.put(f"{team.base}/guardrails", json={"monthly_spend_limit": "1"}, headers=team.headers)
    await scale_spend_to(container, Decimal("1.00"))
    assert (await guardrails(client, team))["limit_reached"] is True

    async with container.database.sessions() as db:
        before = await db.scalar(select(func.count()).select_from(LLMCall))
    refused = await call(client, team_session, credential["id"])
    assert refused.status_code == 402
    error = refused.json()["error"]
    assert error["code"] == "spend_limit_reached"
    assert "monthly spending limit of $1.00 was reached" in error["message"]
    assert "Guardrails" in error["message"]
    async with container.database.sessions() as db:
        assert await db.scalar(select(func.count()).select_from(LLMCall)) == before  # no call, so no record

    await client.put(f"{team.base}/guardrails", json={"monthly_spend_limit": "50"}, headers=team.headers)
    assert (await call(client, team_session, credential["id"])).status_code == 200
    await client.put(f"{team.base}/guardrails", json={"monthly_spend_limit": None}, headers=team.headers)
    assert (await call(client, team_session, credential["id"])).status_code == 200


async def test_the_limit_counts_every_project_of_the_workspace_and_nobody_elses(
    client: httpx.AsyncClient, team: Team, team_session: Session, container: Container
) -> None:
    from tests.integration.teams.conftest import new_project

    other = await new_project(client, team, "Second project")
    second = Session(team.headers, team.users["owner"], other)
    first_key = await add_credential(client, team_session, "mock")
    second_key = await add_credential(client, second, "mock")
    assert (await call(client, team_session, first_key["id"])).status_code == 200
    await client.put(f"{team.base}/guardrails", json={"monthly_spend_limit": "1"}, headers=team.headers)
    await scale_spend_to(container, Decimal("1.00"))
    assert (await call(client, second, second_key["id"])).status_code == 402  # spent in the other project

    # a person's own workspace has no limit of its own
    personal = (await client.post("/api/v1/projects", json={"name": "Mine"}, headers=team.headers)).json()["id"]
    mine = Session(team.headers, team.users["owner"], personal)
    mine_key = await add_credential(client, mine, "mock")
    assert (await call(client, mine, mine_key["id"])).status_code == 200


async def test_a_run_stops_within_one_batch_keeps_its_answers_and_says_why(
    client: httpx.AsyncClient,
    team: Team,
    team_session: Session,
    jobs: InlineJobQueue,
    container: Container,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    models = await approved_project(client, team_session, jobs)
    body = {"models": [{"model_profile_id": models["echo"], "runs": 5}]}
    first = (await client.post(f"{team.proj}/experiments", json=body, headers=team.h("member"))).json()
    await jobs.drain()
    async with container.database.sessions() as db:
        per_call = await db.scalar(select(func.avg(LLMCall.cost)).where(LLMCall.cost.is_not(None)))
    assert per_call
    # one call at a time, and room for half of one more real call under a limit of $1
    monkeypatch.setattr(container.settings, "engine_provider_concurrency", 1)
    await client.put(f"{team.base}/guardrails", json={"monthly_spend_limit": "1"}, headers=team.headers)
    await scale_spend_to(container, Decimal(1) - Decimal(per_call) / 2)

    second = (await client.post(f"{team.proj}/experiments", json=body, headers=team.h("member"))).json()
    await jobs.drain()
    done = (await client.get(f"{team.proj}/experiments/{second['id']}", headers=team.h("member"))).json()
    assert done["status"] == "cancelled"
    assert "monthly spending limit of $1.00" in done["stop_reason"]
    progress = done["progress"][0]
    assert progress["succeeded"] >= 1  # what was answered is kept
    assert progress["skipped"] > 0
    assert progress["failed"] == 0
    assert progress["succeeded"] + progress["skipped"] == progress["total"] == 15
    assert progress["succeeded"] <= 2  # at most the call that was already under way when the limit was reached
    assert first["id"] != second["id"]
    # a new run can't even begin while the limit stands
    third = (await client.post(f"{team.proj}/experiments", json=body, headers=team.h("member"))).json()
    await jobs.drain()
    stopped = (await client.get(f"{team.proj}/experiments/{third['id']}", headers=team.h("member"))).json()
    assert stopped["status"] == "cancelled"
    assert stopped["progress"][0]["succeeded"] == 0
