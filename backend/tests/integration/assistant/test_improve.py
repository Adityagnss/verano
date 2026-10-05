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
from app.modules.assistant.models import PromptCandidate
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
