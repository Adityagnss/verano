"""
Integration test for Improve on the mock provider: failures on the optimize split are
grouped into named clusters, 3 candidates are tested on the optimize split, the best is
confirmed on the holdout split, the verdict is honest (echo never improves), candidates
never become the prompt's latest version, and no holdout case reaches the improvement
model.
"""

import httpx
import pytest
from sqlalchemy import select

from app.core.container import Container
from app.core.jobs import InlineJobQueue
from app.modules.gateway.models import LLMCall
from tests.helpers import Session, approved_project

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
    assert confirmed[0]["outcome"] == "not_better"
    assert "No candidate beat the current prompt" in result["message"]

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
    assert all(str(item["inputs"]["user_message"]) not in sent for item in holdout)
