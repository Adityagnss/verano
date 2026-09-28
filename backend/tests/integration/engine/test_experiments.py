"""
Integration tests for the experiment engine on the mock provider: every call planned once
and recorded completely, a failing call recorded without failing the run, the budget cap
stopping the run with finished results kept, and cancel skipping pending calls.
"""

from typing import Any

import httpx
import pytest
from sqlalchemy import select

from app.core.container import Container
from app.core.jobs import InlineJobQueue
from app.modules.engine.models import TestCaseRun
from tests.helpers import Session, approved_project

pytestmark = [pytest.mark.integration]


def url(session: Session, path: str = "") -> str:
    return f"/api/v1/projects/{session.project_id}/experiments{path}"


async def start(client: httpx.AsyncClient, session: Session, body: dict[str, Any]) -> dict[str, Any]:
    response = await client.post(url(session), json=body, headers=session.headers)
    assert response.status_code == 201, response.text
    experiment: dict[str, Any] = response.json()
    return experiment


async def test_an_experiment_runs_every_call_once_and_records_it(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, container: Container
) -> None:
    models = await approved_project(client, session, jobs)
    body = {
        "models": [
            {"model_profile_id": models["good"], "runs": 2, "params": {"temperature": 0.2, "max_tokens": 10}},
            {"model_profile_id": models["rejected"], "runs": 1},
        ]
    }
    estimate = (await client.post(url(session, "/estimate"), json=body, headers=session.headers)).json()
    assert (estimate["cases"], estimate["calls"], estimate["price_known"]) == (3, 9, True)

    experiment = await start(client, session, body)
    await jobs.drain()
    done = (await client.get(url(session, f"/{experiment['id']}"), headers=session.headers)).json()
    assert done["status"] == "completed"
    progress = {p["model"]: (p["total"], p["succeeded"], p["failed"]) for p in done["progress"]}
    assert progress == {"good": (6, 6, 0), "rejected": (3, 0, 3)}
    async with container.database.sessions() as db:
        rows = list((await db.scalars(select(TestCaseRun).where(TestCaseRun.experiment_id == experiment["id"]))).all())
    ok = next(r for r in rows if r.status == "succeeded")
    recorded = [ok.rendered_system_prompt, ok.rendered_user_prompt, ok.raw_output, ok.input_tokens, ok.cost]
    assert all([*recorded, ok.llm_call_id, ok.trace_id, ok.completed_at])
    assert ok.params == {"temperature": 0.2, "max_tokens": 10}
    failed = next(r for r in rows if r.status == "failed")
    assert (failed.error_type, bool(failed.error_message)) == ("provider_bad_request", True)

    runs = done["estimate"]["models"]
    assert [m["calls"] for m in runs] == [6, 3]
    replay = await start(client, session, body)
    await jobs.drain()
    assert replay["id"] != experiment["id"]


async def test_the_budget_cap_stops_the_run_and_keeps_finished_results(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue
) -> None:
    models = await approved_project(client, session, jobs)
    body = {"models": [{"model_profile_id": models["good"], "runs": 5}], "budget_cap": "0.0000001"}
    experiment = await start(client, session, body)
    await jobs.drain()
    done = (await client.get(url(session, f"/{experiment['id']}"), headers=session.headers)).json()
    assert done["status"] == "cancelled"
    assert "Budget cap" in done["stop_reason"]
    progress = done["progress"][0]
    assert progress["succeeded"] >= 1
    assert progress["skipped"] >= 1
    assert progress["succeeded"] + progress["skipped"] + progress["failed"] == 15


async def test_cancel_skips_pending_calls(client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue) -> None:
    models = await approved_project(client, session, jobs)
    experiment = await start(client, session, {"models": [{"model_profile_id": models["echo"], "runs": 5}]})
    cancelled = await client.post(url(session, f"/{experiment['id']}/cancel"), headers=session.headers)
    await jobs.drain()
    assert cancelled.json()["status"] == "cancelled"
    done = (await client.get(url(session, f"/{experiment['id']}"), headers=session.headers)).json()
    progress = done["progress"][0]
    assert progress["skipped"] > 0
    assert progress["succeeded"] + progress["skipped"] == 15
