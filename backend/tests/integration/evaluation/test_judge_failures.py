"""
Integration tests for a judge that cannot score: the answer is shown as unscored with the reason,
never as a pass or a zero, in Results, the case view, the CSV and the Logbook; and an experiment
whose checks need a judge is refused when none is chosen.
"""

import csv
import io
from typing import Any

import httpx
import pytest
from sqlalchemy import select

from app.core.container import Container
from app.core.jobs import InlineJobQueue
from app.modules.evaluation.models import Score
from tests.helpers import (
    GOLDEN_TICKETS,
    Session,
    add_credential,
    add_golden,
    add_input_files,
    create_prompt,
)

pytestmark = [pytest.mark.integration]

JUDGED = {
    "evaluator_name": "g_eval_correctness",
    "evaluator_version": "1",
    "config": {"kind": "deepeval", "metric": "g_eval", "criteria": "The answer is a correct label."},
    "threshold": 0.5,
    "weight": 1.0,
    "required": False,
}


def base(session: Session) -> str:
    return f"/api/v1/projects/{session.project_id}"


async def judged_project(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, judge: str | None
) -> dict[str, str]:
    """An approved project whose checks include one judged by `judge` (no judge when None)."""
    credential = await add_credential(client, session, "mock")
    version = await create_prompt(client, session, system_template="Classify the support ticket. Reply with one word.")
    await add_input_files(
        client, session, jobs, ["My card was charged twice", "Where is my parcel?", "The app crashes on start"]
    )
    await add_golden(client, session, jobs, "golden.csv", GOLDEN_TICKETS.encode(), {"expected_output": "expected"})
    spec = {"task_type": "classification", "goal": "Classify tickets", "output_format": "single_label"}
    spec["allowed_outputs"] = ["billing", "shipping", "technical"]  # type: ignore[assignment]
    body: dict[str, Any] = {"spec": spec}
    if judge:
        body["judge"] = {"credential_id": credential["id"], "model": judge}
    provided = await client.put(
        f"{base(session)}/prompt-versions/{version['id']}/task-spec", json=body, headers=session.headers
    )
    assert provided.status_code == 200, provided.text
    started = await client.post(
        f"{base(session)}/generations",
        json={"task_spec_id": provided.json()["id"], "golden_only": True},
        headers=session.headers,
    )
    await jobs.drain()
    version_id = started.json()["id"]
    current = (
        await client.get(f"{base(session)}/dataset-versions/{version_id}/evaluators", headers=session.headers)
    ).json()
    evaluators = [{k: e[k] for k in JUDGED} for e in current["evaluators"]]
    edited = await client.put(
        f"{base(session)}/dataset-versions/{version_id}/evaluators",
        json={"evaluators": [*evaluators, JUDGED]},
        headers=session.headers,
    )
    assert edited.status_code == 200, edited.text
    approved = await client.post(f"{base(session)}/dataset-versions/{version_id}/approve", headers=session.headers)
    assert approved.status_code == 200, approved.text
    models = await client.get(f"{base(session)}/models", params={"limit": 200}, headers=session.headers)
    return {m["model_name"]: m["id"] for m in models.json()["items"]}


async def run_good(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, models: dict[str, str]
) -> dict[str, Any]:
    body = {"models": [{"model_profile_id": models["good"], "runs": 2}]}
    response = await client.post(f"{base(session)}/experiments", json=body, headers=session.headers)
    assert response.status_code == 201, response.text
    await jobs.drain()
    experiment: dict[str, Any] = response.json()
    return experiment


async def test_a_judge_that_fails_leaves_every_answer_unscored_never_passed(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, container: Container
) -> None:
    models = await judged_project(client, session, jobs, judge="judge_down")
    experiment = await run_good(client, session, jobs, models)
    path = f"{base(session)}/experiments/{experiment['id']}"

    results = (await client.get(f"{path}/results", headers=session.headers)).json()
    (good,) = results["models"]
    assert (good["cases"], good["judged_cases"], good["unscored_cases"]) == (6, 0, 6)
    assert (good["quality"], good["pass_rate"], good["consistency"]) == (None, None, None)

    cases = (await client.get(f"{path}/cases", headers=session.headers)).json()
    output = cases[0]["outputs"][0]
    assert output["judged"] is False
    unscored = next(s for s in output["scores"] if s["evaluator_name"] == "g_eval_correctness")
    assert unscored["status"] == "unscored"
    assert "The judge could not score this answer" in unscored["reason"]
    assert any(s["status"] == "scored" for s in output["scores"])

    exported = await client.get(f"{path}/export.csv", headers=session.headers)
    rows = list(csv.DictReader(io.StringIO(exported.text)))
    assert {(r["judged"], r["passed"], r["quality"]) for r in rows} == {("no", "", "")}

    async with container.database.sessions() as db:
        statuses = {
            s.status for s in (await db.scalars(select(Score))).all() if s.evaluator_name == JUDGED["evaluator_name"]
        }
    assert statuses == {"unscored"}

    answers = (
        await client.get(f"{base(session)}/logbook/answers", params={"limit": 50}, headers=session.headers)
    ).json()
    assert [(a["passed"], a["quality"]) for a in answers["items"]] == [(None, None)] * 6
    assert all(not a["failed_checks"] for a in answers["items"])


async def test_a_working_judge_scores_every_answer_and_counts_them_as_judged(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue
) -> None:
    models = await judged_project(client, session, jobs, judge="scripted")
    experiment = await run_good(client, session, jobs, models)
    results = (
        await client.get(f"{base(session)}/experiments/{experiment['id']}/results", headers=session.headers)
    ).json()
    (good,) = results["models"]
    assert (good["judged_cases"], good["unscored_cases"]) == (6, 0)
    assert good["quality"] is not None
    cases = (await client.get(f"{base(session)}/experiments/{experiment['id']}/cases", headers=session.headers)).json()
    assert all(o["judged"] for case in cases for o in case["outputs"])


async def test_checks_that_need_a_judge_refuse_to_run_without_one(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue
) -> None:
    models = await judged_project(client, session, jobs, judge=None)
    body = {"models": [{"model_profile_id": models["good"]}]}
    for path in ("/experiments/estimate", "/experiments"):
        refused = await client.post(f"{base(session)}{path}", json=body, headers=session.headers)
        assert refused.status_code == 422, path
        assert "no judge model is chosen" in refused.json()["error"]["message"]
