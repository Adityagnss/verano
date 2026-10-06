"""The Activity page sums the workspace's recorded calls per day, per model, key and project."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
from sqlalchemy import update

from app.core.container import Container
from app.modules.gateway.models import LLMCall
from tests.helpers import Session, add_credential, sign_up


async def call(client: httpx.AsyncClient, session: Session, project_id: str, credential_id: str) -> None:
    body = {"credential_id": credential_id, "model": "echo", "messages": [{"role": "user", "content": "hello gateway"}]}
    response = await client.post(f"/api/v1/projects/{project_id}/llm-calls", json=body, headers=session.headers)
    assert response.status_code == 200, response.text


async def test_activity_covers_every_project_of_the_workspace_and_compares_with_the_period_before(
    client: httpx.AsyncClient, session: Session, container: Container
) -> None:
    first = await add_credential(client, session, "mock")
    other = (await client.post("/api/v1/projects", json={"name": "Second"}, headers=session.headers)).json()
    second = await add_credential(client, Session(session.headers, session.user_id, other["id"]), "mock")
    await call(client, session, str(session.project_id), first["id"])
    await call(client, session, str(session.project_id), first["id"])
    await call(client, session, other["id"], second["id"])
    async with container.database.sessions() as db:  # one call moved into the period before
        earliest = (await db.execute(LLMCall.__table__.select().order_by(LLMCall.id).limit(1))).first()
        assert earliest is not None
        await db.execute(
            update(LLMCall).where(LLMCall.id == earliest.id).values(started_at=datetime.now(UTC) - timedelta(days=10))
        )
        await db.commit()
    stranger = await sign_up(client, "stranger@example.com")
    assert (await client.get("/api/v1/activity", headers=stranger)).json()["rows"] == []

    response = await client.get("/api/v1/activity", params={"days": 7, "tz": "Asia/Kolkata"}, headers=session.headers)
    assert response.status_code == 200, response.text
    body = response.json()
    current = [r for r in body["rows"] if r["period"] == "current"]
    prior = [r for r in body["rows"] if r["period"] == "prior"]
    assert sum(r["requests"] for r in current) == 2
    assert sum(r["requests"] for r in prior) == 1
    assert {r["model"] for r in body["rows"]} == {"echo"}
    assert sum(Decimal(r["cost"]) for r in current) == Decimal("0.000016")
    assert {p["name"] for p in body["projects"]} == {"Support triage", "Second"}
    (key,) = body["keys"]  # the same mock "key" in two projects is one key
    assert (key["provider"], key["projects"]) == ("mock", 2)
    assert {r["key"] for r in body["rows"]} == {key["id"]}

    bad = await client.get("/api/v1/activity", params={"tz": "Mars/Olympus"}, headers=session.headers)
    assert bad.status_code == 422
    assert "Unknown time zone" in bad.json()["error"]["message"]
