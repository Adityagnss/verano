"""
Integration test for Improve on the mock provider: failures on the optimize split are
grouped into named clusters, 3 candidates are tested on the optimize split, the best is
confirmed on the holdout split, the verdict is honest (echo never improves), candidates
never become the prompt's latest version, and no holdout case reaches the improvement
model.
"""

import uuid
from typing import Any

import httpx
import pytest
from sqlalchemy import select

from app.core.container import Container
from app.core.jobs import InlineJobQueue
from app.modules.assistant.models import OptimizationSession, PromptCandidate
from app.modules.assistant.pipeline import ImprovementPipeline
from app.modules.assistant.schemas import CandidateOutcome
from app.modules.gateway.models import LLMCall
from tests.helpers import Session, approved_project, approved_project_with_cases

pytestmark = [pytest.mark.integration]


async def test_improve_uses_only_optimize_failures_and_reports_honestly(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, container: Container
) -> None:
    base = f"/api/v1/projects/{session.project_id}"
    models = await approved_project(client, session, jobs)
    body = {"models": [{"model_profile_id": models["echo"], "runs": 1}]}
    experiment = (await client.post(f"{base}/experiments", json=body, headers=session.headers)).json()
    await jobs.drain()
    before = (await client.get(f"{base}/prompts", headers=session.headers)).json()["items"][0]["latest_version"]

    started = await client.post(
        f"{base}/improvements", json={"experiment_id": experiment["id"]}, headers=session.headers
    )
    assert started.status_code == 202, started.text
    await jobs.drain()
    result = (
        await client.get(
            f"{base}/improvements/latest", params={"experiment_id": experiment["id"]}, headers=session.headers
        )
    ).json()

    assert result["stage"] == "done"
    assert [c["name"] for c in result["clusters"]] == ["Echoes the ticket"]
    assert result["clusters"][0]["rule_tag"] == "format_broken"
    assert len(result["candidates"]) == 3
    assert all(c["optimize_experiment_id"] and c["diff"].startswith("--- current") for c in result["candidates"])
    confirmed = [c for c in result["candidates"] if c["holdout_experiment_id"]]
    assert len(confirmed) == 1
    for candidate in result["candidates"]:
        scored = (
            await client.get(f"{base}/experiments/{candidate['optimize_experiment_id']}", headers=session.headers)
        ).json()
        assert scored["evaluator_set_version_id"] == experiment["evaluator_set_version_id"]
    assert confirmed[0]["outcome"] == "not_better"
    assert result["message"].startswith("Not proven")
    prompt_id = before["prompt_id"]
    listed = (await client.get(f"{base}/prompts/{prompt_id}/versions", headers=session.headers)).json()["items"]
    assert [v["id"] for v in listed] == [before["id"]]  # candidates are not saved versions
    proof = confirmed[0]["verdict"]
    assert proof["reason"] == "too_few_cases"
    assert proof["minimum_cases"] == 30
    assert proof["message"] == result["message"]
    assert proof["comparison"]["cases"] < 30

    after = (await client.get(f"{base}/prompts", headers=session.headers)).json()["items"][0]["latest_version"]
    assert after["id"] == before["id"]
    accept = f"{base}/improvements/{result['id']}/candidates/{confirmed[0]['id']}/accept"
    assert (await client.post(accept, headers=session.headers)).status_code == 409

    version_id = experiment["dataset_version_id"]
    holdout = (
        await client.get(
            f"{base}/dataset-versions/{version_id}/items", params={"split": "holdout"}, headers=session.headers
        )
    ).json()["items"]
    async with container.database.sessions() as db:
        calls = list((await db.scalars(select(LLMCall).where(LLMCall.purpose == "assistant"))).all())
    assert {call.labels["step"] for call in calls} == {"failure_groups", "candidates"}
    sent = " ".join(str(call.request_messages) for call in calls)
    assert holdout
    assert all(str(item["inputs"]["attachment"]) not in sent for item in holdout)


async def improve(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, experiment_id: str
) -> dict[str, Any]:
    base = f"/api/v1/projects/{session.project_id}"
    started = await client.post(f"{base}/improvements", json={"experiment_id": experiment_id}, headers=session.headers)
    assert started.status_code == 202, started.text
    await jobs.drain()
    latest = await client.get(
        f"{base}/improvements/latest", params={"experiment_id": experiment_id}, headers=session.headers
    )
    result: dict[str, Any] = latest.json()
    return result


async def test_enough_holdout_cases_and_no_real_gain_is_not_proven_with_the_numbers(
    client: httpx.AsyncClient,
    session: Session,
    jobs: InlineJobQueue,
    container: Container,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(container.settings, "dataset_min_holdout", 10)
    base = f"/api/v1/projects/{session.project_id}"
    models = await approved_project_with_cases(client, session, jobs, count=40)
    body = {"models": [{"model_profile_id": models["echo"], "runs": 1}]}
    experiment = (await client.post(f"{base}/experiments", json=body, headers=session.headers)).json()
    await jobs.drain()
    result = await improve(client, session, jobs, experiment["id"])
    chosen = next(c for c in result["candidates"] if c["holdout_experiment_id"])
    proof = chosen["verdict"]
    assert proof["reason"] == "not_proven"
    assert proof["comparison"]["cases"] >= 10
    assert proof["comparison"]["label"] == "no clear difference"
    assert proof["comparison"]["difference"] == pytest.approx(0.0)
    assert "within chance" in result["message"]
    accept = f"{base}/improvements/{result['id']}/candidates/{chosen['id']}/accept"
    refused = await client.post(accept, headers=session.headers)
    assert refused.status_code == 409


async def test_only_a_proven_candidate_can_be_accepted_and_it_becomes_a_new_prompt_version(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, container: Container
) -> None:
    base = f"/api/v1/projects/{session.project_id}"
    models = await approved_project(client, session, jobs)
    body = {"models": [{"model_profile_id": models["echo"], "runs": 1}]}
    experiment = (await client.post(f"{base}/experiments", json=body, headers=session.headers)).json()
    await jobs.drain()
    before = (await client.get(f"{base}/prompts", headers=session.headers)).json()["items"][0]["latest_version"]
    result = await improve(client, session, jobs, experiment["id"])
    chosen = next(c for c in result["candidates"] if c["holdout_experiment_id"])
    accept = f"{base}/improvements/{result['id']}/candidates/{chosen['id']}/accept"
    assert (await client.post(accept, headers=session.headers)).status_code == 409
    async with container.database.sessions() as db:
        row = await db.get(PromptCandidate, uuid.UUID(chosen["id"]))
        assert row is not None
        row.outcome = CandidateOutcome.BETTER
        await db.commit()
    accepted = await client.post(accept, headers=session.headers)
    assert accepted.status_code == 200, accepted.text
    prompt = (await client.get(f"{base}/prompts", headers=session.headers)).json()["items"][0]["latest_version"]
    assert prompt["id"] != before["id"]
    assert prompt["change_reason"].startswith("Accepted improvement")


async def test_improve_can_start_again_with_a_chosen_writer_model(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue
) -> None:
    base = f"/api/v1/projects/{session.project_id}"
    models = await approved_project(client, session, jobs)
    body = {"models": [{"model_profile_id": models["echo"], "runs": 1}]}
    experiment = (await client.post(f"{base}/experiments", json=body, headers=session.headers)).json()
    await jobs.drain()
    first = await improve(client, session, jobs, experiment["id"])
    judge = (await client.get(f"{base}/experiments/{experiment['id']}", headers=session.headers)).json()["config"][
        "judge"
    ]
    assert first["writer_model"] == judge["model"]

    wrong = {"experiment_id": experiment["id"], "writer": {"credential_id": judge["credential_id"], "model": "no-such"}}
    refused = await client.post(f"{base}/improvements", json=wrong, headers=session.headers)
    assert refused.status_code >= 400
    again = {"experiment_id": experiment["id"], "writer": judge}
    started = await client.post(f"{base}/improvements", json=again, headers=session.headers)
    assert started.status_code == 202, started.text
    await jobs.drain()
    latest = (
        await client.get(
            f"{base}/improvements/latest", params={"experiment_id": experiment["id"]}, headers=session.headers
        )
    ).json()
    assert latest["id"] != first["id"]
    assert latest["writer_model"] == judge["model"]


async def test_any_candidate_can_be_saved_as_a_prompt_version_to_test(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue
) -> None:
    base = f"/api/v1/projects/{session.project_id}"
    models = await approved_project(client, session, jobs)
    body = {"models": [{"model_profile_id": models["echo"], "runs": 1}]}
    experiment = (await client.post(f"{base}/experiments", json=body, headers=session.headers)).json()
    await jobs.drain()
    before = (await client.get(f"{base}/prompts", headers=session.headers)).json()["items"][0]["latest_version"]
    result = await improve(client, session, jobs, experiment["id"])
    chosen = result["candidates"][0]
    assert chosen["outcome"] != "better"  # not proven, and still saveable
    assert chosen["system_template"] or chosen["user_template"]  # the page can show the full prompt

    saved = await client.post(
        f"{base}/improvements/{result['id']}/candidates/{chosen['id']}/save", headers=session.headers
    )
    assert saved.status_code == 200, saved.text
    latest = (await client.get(f"{base}/prompts", headers=session.headers)).json()["items"][0]["latest_version"]
    assert latest["id"] != before["id"]
    assert latest["version"] == before["version"] + 1
    assert latest["system_template"] == chosen["system_template"]
    # the candidate's own result is untouched, and it can be tested like any saved version
    again = (await client.get(f"{base}/improvements/{result['id']}", headers=session.headers)).json()
    assert next(c for c in again["candidates"] if c["id"] == chosen["id"])["outcome"] == chosen["outcome"]
    rerun = {**body, "prompt_version_id": latest["id"]}
    assert (await client.post(f"{base}/experiments", json=rerun, headers=session.headers)).status_code in (
        200,
        201,
        202,
    )


async def test_a_stopped_improvement_keeps_everything_and_continues_where_it_left_off(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, container: Container
) -> None:
    base = f"/api/v1/projects/{session.project_id}"
    models = await approved_project(client, session, jobs)
    body = {"models": [{"model_profile_id": models["echo"], "runs": 1}]}
    experiment = (await client.post(f"{base}/experiments", json=body, headers=session.headers)).json()
    await jobs.drain()
    result = await improve(client, session, jobs, experiment["id"])
    assert result["stage"] == "done"
    sid = result["id"]
    assert (await client.post(f"{base}/improvements/{sid}/stop", headers=session.headers)).status_code == 409
    assert (await client.post(f"{base}/improvements/{sid}/continue", headers=session.headers)).status_code == 409

    # put the session back where a stop in the middle of testing leaves it: one candidate never tested
    untested = result["candidates"][0]["id"]
    async with container.database.sessions() as db:
        row = await db.get(OptimizationSession, uuid.UUID(sid))
        candidate = await db.get(PromptCandidate, uuid.UUID(untested))
        assert row is not None
        assert candidate is not None
        row.stage = "testing"
        candidate.optimize_experiment_id = None
        for other in (await db.scalars(select(PromptCandidate).where(PromptCandidate.session_id == row.id))).all():
            other.holdout_experiment_id = None  # no candidate has reached the holdout yet
            other.outcome = CandidateOutcome.PENDING
        await db.commit()
    response = await client.post(f"{base}/improvements/{sid}/stop", headers=session.headers)
    assert response.status_code == 200, response.text
    stopped = response.json()
    assert stopped["stage"] == "stopped"
    assert len(stopped["candidates"]) == 3
    assert len(stopped["clusters"]) == len(result["clusters"])

    resumed = await client.post(f"{base}/improvements/{sid}/continue", headers=session.headers)
    assert resumed.status_code == 202, resumed.text
    await jobs.drain()
    done = (await client.get(f"{base}/improvements/{sid}", headers=session.headers)).json()
    assert done["stage"] == "done"
    assert len(done["candidates"]) == 3
    retried = next(c for c in done["candidates"] if c["id"] == untested)
    assert retried["optimize_experiment_id"], (retried["outcome"], done["message"])


async def test_a_job_error_ends_the_improvement_as_failed_with_the_reason(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = f"/api/v1/projects/{session.project_id}"
    models = await approved_project(client, session, jobs)
    body = {"models": [{"model_profile_id": models["echo"], "runs": 1}]}
    experiment = (await client.post(f"{base}/experiments", json=body, headers=session.headers)).json()
    await jobs.drain()

    async def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(ImprovementPipeline, "_improve", boom)
    result = await improve(client, session, jobs, experiment["id"])
    assert result["stage"] == "failed"
    assert result["message"] == "Something went wrong: boom"


async def test_history_lists_improvements_and_a_candidate_is_saved_and_tested_in_one_go(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue
) -> None:
    base = f"/api/v1/projects/{session.project_id}"
    models = await approved_project(client, session, jobs)
    body = {"models": [{"model_profile_id": models["echo"], "runs": 1}]}
    experiment = (await client.post(f"{base}/experiments", json=body, headers=session.headers)).json()
    await jobs.drain()
    result = await improve(client, session, jobs, experiment["id"])

    history = (await client.get(f"{base}/improvements", headers=session.headers)).json()
    assert [(h["id"], h["stage"], h["candidate_count"]) for h in history] == [(result["id"], "done", 3)]
    assert history[0]["best_strategy"]

    chosen = result["candidates"][0]
    ref = (
        await client.get(
            f"{base}/improvements/candidate-for/{chosen['optimize_experiment_id']}", headers=session.headers
        )
    ).json()
    assert (ref["session_id"], ref["candidate_id"]) == (result["id"], chosen["id"])
    assert (
        await client.get(f"{base}/improvements/candidate-for/{experiment['id']}", headers=session.headers)
    ).json() is None

    save = f"{base}/improvements/{result['id']}/candidates/{chosen['id']}/save"
    first = await client.post(save, params={"run": "true"}, headers=session.headers)
    assert first.status_code == 200, first.text
    started = (
        await client.get(f"{base}/experiments/{first.json()['started_experiment_id']}", headers=session.headers)
    ).json()
    assert started["origin"] == "manual"  # a test of your own now, on all the test cases
    assert started["split_scope"] == experiment["split_scope"]
    prompt = (await client.get(f"{base}/prompts", headers=session.headers)).json()["items"][0]
    assert started["prompt_version_id"] == prompt["latest_version"]["id"]

    again = await client.post(save, headers=session.headers)  # pressing it twice does not make a second version
    assert again.status_code == 200
    versions = (await client.get(f"{base}/prompts/{prompt['id']}/versions", headers=session.headers)).json()["items"]
    assert len(versions) == 2
