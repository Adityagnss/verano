"""
Integration tests for the Phase 9 engine hardening: pause at the cap and resume with no call repeated (S9.6), pause,
resume and retry-failed with their guards, the ETA, the live events stream, sample size, and the lease sweeper that
returns work from dead workers to pending so the jobs finish (S9.7). A killed worker is simulated the way it looks
in the database: a row still "running" whose lease has run out, with the inline job queue standing in for the broker.
"""

import json
from datetime import timedelta
from itertools import pairwise
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select, update

from app.core.container import Container
from app.core.jobs import InlineJobQueue
from app.core.security import utcnow
from app.modules.engine.models import Experiment, TestCaseRun
from app.modules.engine.sweeper import LeaseSweeper
from app.modules.evaluation.models import EvaluationRun
from app.modules.gateway.models import LLMCall
from tests.helpers import Session, approved_project, judged_project

pytestmark = [pytest.mark.integration]


def base(session: Session) -> str:
    return f"/api/v1/projects/{session.project_id}/experiments"


async def start(client: httpx.AsyncClient, session: Session, body: dict[str, Any]) -> dict[str, Any]:
    response = await client.post(base(session), json=body, headers=session.headers)
    assert response.status_code == 201, response.text
    experiment: dict[str, Any] = response.json()
    return experiment


async def fetch(client: httpx.AsyncClient, session: Session, experiment_id: str) -> dict[str, Any]:
    response = await client.get(f"{base(session)}/{experiment_id}", headers=session.headers)
    body: dict[str, Any] = response.json()
    return body


async def statuses(container: Container, experiment_id: str) -> dict[str, int]:
    async with container.database.sessions() as db:
        rows = await db.execute(
            select(TestCaseRun.status, func.count())
            .where(TestCaseRun.experiment_id == experiment_id)
            .group_by(TestCaseRun.status)
        )
        return {str(status.value): count for status, count in rows.all()}


async def test_pausing_at_the_cap_then_resuming_with_a_higher_cap_repeats_no_call(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, container: Container
) -> None:
    models = await approved_project(client, session, jobs)
    experiment = await start(
        client, session, {"models": [{"model_profile_id": models["good"], "runs": 5}], "budget_cap": "0.0000001"}
    )
    await jobs.drain()
    paused = await fetch(client, session, experiment["id"])
    assert paused["status"] == "paused"
    async with container.database.sessions() as db:
        before = {c.test_case_run_id: c.id for c in (await db.scalars(select(LLMCall))).all() if c.test_case_run_id}
    assert 1 <= len(before) < 15

    too_low = await client.post(
        f"{base(session)}/{experiment['id']}/resume", json={"budget_cap": "0.0000001"}, headers=session.headers
    )
    assert too_low.status_code == 422 and "Raise the budget cap" in too_low.text

    resumed = await client.post(
        f"{base(session)}/{experiment['id']}/resume", json={"budget_cap": "50"}, headers=session.headers
    )
    assert resumed.status_code == 200, resumed.text
    await jobs.drain()
    async with container.database.sessions() as db:
        calls = [c for c in (await db.scalars(select(LLMCall))).all() if c.test_case_run_id]
    by_run = {c.test_case_run_id: c.id for c in calls}
    assert len(calls) == len(by_run) == 15  # one call per planned call: nothing was made twice
    assert all(by_run[run_id] == call_id for run_id, call_id in before.items())  # the earlier calls are the same rows
    done = await fetch(client, session, experiment["id"])
    assert done["status"] == "completed"
    assert (await client.post(f"{base(session)}/{experiment['id']}/resume", headers=session.headers)).status_code == 409


async def test_a_person_can_pause_and_resume_and_the_guards_say_why_not(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue
) -> None:
    models = await approved_project(client, session, jobs)
    experiment = await start(client, session, {"models": [{"model_profile_id": models["echo"], "runs": 3}]})
    paused = await client.post(f"{base(session)}/{experiment['id']}/pause", headers=session.headers)
    assert paused.status_code == 200 and paused.json()["status"] == "paused"
    assert "Resume" in paused.json()["stop_reason"]
    again = await client.post(f"{base(session)}/{experiment['id']}/pause", headers=session.headers)
    assert again.status_code == 409
    await jobs.drain()
    assert (await fetch(client, session, experiment["id"]))["status"] == "paused"  # nothing ran while paused
    assert (
        await client.post(f"{base(session)}/{experiment['id']}/retry-failed", headers=session.headers)
    ).status_code == 409

    resumed = await client.post(f"{base(session)}/{experiment['id']}/resume", headers=session.headers)
    assert resumed.status_code == 200
    await jobs.drain()
    done = await fetch(client, session, experiment["id"])
    assert done["status"] == "completed" and done["progress"][0]["succeeded"] == 9
    for action in ("pause", "retry-failed"):
        refused = await client.post(f"{base(session)}/{experiment['id']}/{action}", headers=session.headers)
        assert refused.status_code == 409


async def test_resuming_a_run_whose_calls_all_finished_while_paused_moves_on_to_scoring(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, container: Container
) -> None:
    """A real bug found by the tests: resume with no pending call used to leave the run 'running' for ever."""
    models = await approved_project(client, session, jobs)
    experiment = await start(client, session, {"models": [{"model_profile_id": models["echo"], "runs": 1}]})
    await client.post(f"{base(session)}/{experiment['id']}/pause", headers=session.headers)
    await jobs.drain()
    async with container.database.sessions() as db:
        await db.execute(
            update(TestCaseRun)
            .where(TestCaseRun.experiment_id == experiment["id"])
            .values(status="succeeded", raw_output="billing", completed_at=utcnow())
        )
        await db.commit()
    resumed = await client.post(f"{base(session)}/{experiment['id']}/resume", headers=session.headers)
    assert resumed.status_code == 200
    await jobs.drain()
    assert (await fetch(client, session, experiment["id"]))["status"] == "completed"


async def test_retry_failed_requeues_calls_that_failed_for_a_passing_reason_only(
    client: httpx.AsyncClient,
    session: Session,
    jobs: InlineJobQueue,
    container: Container,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(container.settings, "breaker_failure_threshold", 1_000)
    monkeypatch.setattr(container.settings, "llm_backoff_base_s", 0.001)
    monkeypatch.setattr(container.settings, "llm_backoff_max_s", 0.002)
    models = await approved_project(client, session, jobs)
    body = {
        "models": [
            {"model_profile_id": models["down"], "runs": 1},
            {"model_profile_id": models["rejected"], "runs": 1},
        ]
    }
    experiment = await start(client, session, body)
    await jobs.drain()
    before = await statuses(container, experiment["id"])
    assert before == {"failed": 6}  # the provider was down (3) and a bad request (3: not worth retrying)
    async with container.database.sessions() as db:
        await db.execute(update(Experiment).where(Experiment.id == experiment["id"]).values(status="paused"))
        await db.commit()

    retried = await client.post(f"{base(session)}/{experiment['id']}/retry-failed", headers=session.headers)
    assert retried.status_code == 200, retried.text
    assert await statuses(container, experiment["id"]) == {"failed": 3, "pending": 3}
    nothing = await client.post(f"{base(session)}/{experiment['id']}/retry-failed", headers=session.headers)
    assert nothing.status_code == 409


async def test_the_eta_appears_once_calls_have_finished_and_a_sample_limits_the_cases(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, container: Container
) -> None:
    models = await approved_project(client, session, jobs)
    experiment = await start(client, session, {"models": [{"model_profile_id": models["echo"], "runs": 2}]})
    await client.post(f"{base(session)}/{experiment['id']}/pause", headers=session.headers)
    await jobs.drain()
    assert (await fetch(client, session, experiment["id"]))["eta_seconds"] is None
    async with container.database.sessions() as db:
        ids = list(
            (await db.scalars(select(TestCaseRun.id).where(TestCaseRun.experiment_id == experiment["id"]))).all()
        )
        await db.execute(
            update(TestCaseRun).where(TestCaseRun.id.in_(ids[:2])).values(status="succeeded", completed_at=utcnow())
        )
        await db.execute(
            update(Experiment)
            .where(Experiment.id == experiment["id"])
            .values(status="running", started_at=utcnow() - timedelta(seconds=10))
        )
        await db.commit()
    running = await fetch(client, session, experiment["id"])
    assert running["eta_seconds"] is not None and running["eta_seconds"] >= 1
    started = await fetch(client, session, experiment["id"])
    assert started["status"] == "running"

    sample = await start(client, session, {"models": [{"model_profile_id": models["echo"]}], "sample_size": 2})
    await jobs.drain()
    done = await fetch(client, session, sample["id"])
    assert done["progress"][0]["total"] == 2


async def test_the_events_stream_sends_progress_and_closes_when_the_run_ends(
    client: httpx.AsyncClient,
    session: Session,
    jobs: InlineJobQueue,
    container: Container,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(container.settings, "sse_poll_s", 0.01)
    monkeypatch.setattr(container.settings, "sse_idle_poll_s", 0.02)
    models = await approved_project(client, session, jobs)
    experiment = await start(client, session, {"models": [{"model_profile_id": models["echo"], "runs": 1}]})
    url = f"{base(session)}/{experiment['id']}/events"
    async with client.stream("GET", url, headers=session.headers) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = "".join([chunk async for chunk in response.aiter_text()])  # returns only because the stream closes
    await jobs.drain()
    events = [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: ")]
    assert events and events[-1]["status"] == "succeeded" and events[-1]["stage"] == "completed"
    assert events[-1]["processed"] == events[-1]["total"] == 3
    assert all(a != b for a, b in pairwise(events))  # an event only when something changed
    missing = await client.get(f"{base(session)}/00000000-0000-0000-0000-000000000000/events", headers=session.headers)
    assert missing.status_code == 404
    assert (await client.get(url)).status_code == 401


async def test_a_killed_worker_mid_generation_of_calls_leaves_nothing_running_and_the_run_finishes(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, container: Container
) -> None:
    models = await approved_project(client, session, jobs)
    experiment = await start(client, session, {"models": [{"model_profile_id": models["echo"], "runs": 3}]})
    await jobs.drain()
    assert (await fetch(client, session, experiment["id"]))["status"] == "completed"
    async with container.database.sessions() as db:
        ids = list(
            (await db.scalars(select(TestCaseRun.id).where(TestCaseRun.experiment_id == experiment["id"]))).all()
        )
        await db.execute(
            update(TestCaseRun)
            .where(TestCaseRun.id.in_(ids[:4]))
            .values(status="running", started_at=utcnow(), completed_at=None, raw_output=None, llm_call_id=None)
            .execution_options(synchronize_session=False)
        )
        await db.execute(
            update(TestCaseRun)
            .where(TestCaseRun.id.in_(ids[:4]))
            .values(lease_expires_at=utcnow() - timedelta(seconds=5))
        )
        await db.execute(update(Experiment).where(Experiment.id == experiment["id"]).values(status="running"))
        await db.commit()
    async with container.database.sessions() as db:
        early = await LeaseSweeper(db, container.settings, container.jobs).sweep()
    assert early.calls == 4 and early.total == 4
    await jobs.drain()
    done = await fetch(client, session, experiment["id"])
    assert done["status"] == "completed"
    assert await statuses(container, experiment["id"]) == {"succeeded": 9}
    async with container.database.sessions() as db:
        quiet = await LeaseSweeper(db, container.settings, container.jobs).sweep()
    assert quiet.total == 0  # nothing left to return


async def test_a_run_whose_worker_died_after_the_last_call_is_moved_on_to_scoring(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, container: Container
) -> None:
    models = await approved_project(client, session, jobs)
    experiment = await start(client, session, {"models": [{"model_profile_id": models["echo"], "runs": 1}]})
    await jobs.drain()
    async with container.database.sessions() as db:
        await db.execute(update(Experiment).where(Experiment.id == experiment["id"]).values(status="running"))
        await db.commit()
    async with container.database.sessions() as db:
        found = await LeaseSweeper(db, container.settings, container.jobs).sweep()
    assert found.runs_finished == 1
    await jobs.drain()
    assert (await fetch(client, session, experiment["id"]))["status"] == "completed"


async def test_a_killed_worker_mid_scoring_returns_the_pass_to_pending_and_scoring_finishes(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, container: Container
) -> None:
    models = await judged_project(client, session, jobs, set_judge="echo")
    experiment = await start(client, session, {"models": [{"model_profile_id": models["echo"], "runs": 1}]})
    await jobs.drain()
    assert (await fetch(client, session, experiment["id"]))["status"] == "completed"
    async with container.database.sessions() as db:
        run = (await db.scalars(select(EvaluationRun).where(EvaluationRun.experiment_id == experiment["id"]))).first()
        assert run is not None
        await db.execute(
            update(EvaluationRun)
            .where(EvaluationRun.id == run.id)
            .values(status="running", completed_at=None, lease_expires_at=utcnow() - timedelta(seconds=5))
        )
        await db.execute(update(Experiment).where(Experiment.id == experiment["id"]).values(status="evaluating"))
        await db.commit()
    async with container.database.sessions() as db:
        found = await LeaseSweeper(db, container.settings, container.jobs).sweep()
    assert found.scoring_passes == 1
    await jobs.drain()
    async with container.database.sessions() as db:
        run = await db.get(EvaluationRun, run.id)
        assert run is not None and run.status == "completed" and run.lease_expires_at is None
        still = await db.scalar(
            select(func.count()).select_from(EvaluationRun).where(EvaluationRun.status == "running")
        )
    assert still == 0
    assert (await fetch(client, session, experiment["id"]))["status"] == "completed"
