"""
Integration tests for editing what the judge is asked and seeing what it saw: criteria or evaluation steps are
checked when saved, an edit after approval is a new evaluator-set version that never touches the frozen dataset
(and an edit that changes nothing is refused), every judge call about an answer can be read exactly as sent, and
the judge can be tried on one answer, with its cost shown first, without changing any result.
"""

import copy
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select

from app.core.container import Container
from app.core.jobs import InlineJobQueue
from app.modules.evaluation.models import EvaluationRun, EvaluatorSetVersion
from tests.helpers import JUDGED, Session, base, judged_project, run_good

pytestmark = [pytest.mark.integration]

STEPS = ["Compare the label with the expected label.", "Fail anything that is not one of the allowed labels."]


def sent(call: dict[str, Any]) -> str:
    return "\n".join(str(m["content"]) for m in call["request_messages"])


async def versions(container: Container) -> int:
    async with container.database.sessions() as db:
        return int(await db.scalar(select(func.count()).select_from(EvaluatorSetVersion)) or 0)


async def setup(client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue) -> tuple[dict[str, str], str, str]:
    models = await judged_project(client, session, jobs, set_judge="scripted")
    experiment = await run_good(client, session, jobs, models)
    path = f"{base(session)}/experiments/{experiment['id']}"
    cases = (await client.get(f"{path}/cases", headers=session.headers)).json()
    return models, path, cases[0]["outputs"][0]["test_case_run_id"]


def edited(**config: Any) -> dict[str, Any]:
    check = copy.deepcopy(JUDGED)
    check["config"] = {"kind": "deepeval", "metric": "g_eval", **config}
    return check


async def shown_version(client: httpx.AsyncClient, session: Session, path: str) -> dict[str, Any]:
    results = (await client.get(f"{path}/results", headers=session.headers)).json()
    version_id = results["evaluation_run"]["evaluator_set_version_id"]
    return dict(
        (await client.get(f"{base(session)}/evaluator-set-versions/{version_id}", headers=session.headers)).json()
    )


@pytest.mark.parametrize(
    ("config", "message"),
    [
        ({}, "needs criteria or evaluation steps"),
        ({"criteria": "   "}, "needs criteria or evaluation steps"),
        ({"evaluation_steps": ["", "  "]}, "needs criteria or evaluation steps"),
        ({"evaluation_steps": [f"step {i}" for i in range(11)]}, "at most 10 evaluation steps"),
        ({"criteria": "x" * 4001}, "at most 4000 characters"),
    ],
)
async def test_a_judged_check_must_say_what_to_judge_and_within_limits(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, config: dict[str, Any], message: str
) -> None:
    _, path, _ = await setup(client, session, jobs)
    answer = await client.post(
        f"{path}/rescore/estimate", json={"evaluators": [edited(**config)]}, headers=session.headers
    )
    assert answer.status_code == 422
    assert message in answer.text


async def test_an_edit_after_approval_is_a_new_version_the_dataset_stays_frozen_and_edits_are_consecutive(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, container: Container
) -> None:
    models, path, _ = await setup(client, session, jobs)
    first = await shown_version(client, session, path)
    dataset = (
        await client.get(f"{base(session)}/dataset-versions/{models['_dataset_version']}", headers=session.headers)
    ).json()
    count = await versions(container)

    one = await client.post(
        f"{path}/rescore",
        json={"evaluators": [edited(criteria="The answer is exactly one allowed label.")]},
        headers=session.headers,
    )
    assert one.status_code == 202, one.text
    await jobs.drain()
    second = await shown_version(client, session, path)
    assert second["version"] == first["version"] + 1
    assert second["change_reason"] == "Checks edited."
    assert second["judge"] == first["judge"]
    assert second["evaluators"][0]["config"]["criteria"] == "The answer is exactly one allowed label."

    two = await client.post(
        f"{path}/rescore", json={"evaluators": [edited(evaluation_steps=STEPS)]}, headers=session.headers
    )
    assert two.status_code == 202, two.text
    await jobs.drain()
    third = await shown_version(client, session, path)
    assert third["version"] == second["version"] + 1
    assert await versions(container) == count + 2

    again = (
        await client.get(f"{base(session)}/dataset-versions/{models['_dataset_version']}", headers=session.headers)
    ).json()
    assert again == dataset
    runs = (await client.get(f"{path}/results", headers=session.headers)).json()["evaluation_runs"]
    assert [r["trigger"] for r in runs] == ["rescore", "rescore", "initial"]


async def test_an_edit_that_changes_nothing_makes_no_version_and_no_scoring_pass(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, container: Container
) -> None:
    _, path, _ = await setup(client, session, jobs)
    current = await shown_version(client, session, path)
    same = [{k: v for k, v in e.items() if k not in ("id", "position")} for e in current["evaluators"]]
    count = await versions(container)
    async with container.database.sessions() as db:
        passes = int(await db.scalar(select(func.count()).select_from(EvaluationRun)) or 0)

    refused = await client.post(f"{path}/rescore", json={"evaluators": same}, headers=session.headers)
    assert refused.status_code == 409
    assert "Nothing was changed" in refused.text
    padded = copy.deepcopy(same)
    padded[-1]["config"]["criteria"] = "  " + padded[-1]["config"]["criteria"] + "  "
    spaced = await client.post(f"{path}/rescore", json={"evaluators": padded}, headers=session.headers)
    assert spaced.status_code == 409
    await jobs.drain()
    assert await versions(container) == count
    async with container.database.sessions() as db:
        assert int(await db.scalar(select(func.count()).select_from(EvaluationRun)) or 0) == passes


async def test_a_check_that_does_not_exist_is_refused_and_score_again_keeps_the_edited_checks(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue
) -> None:
    _, path, _ = await setup(client, session, jobs)
    current = await shown_version(client, session, path)
    wrong = [{k: v for k, v in e.items() if k not in ("id", "position")} for e in current["evaluators"]]
    wrong[0] = {**wrong[0], "evaluator_name": "no_such_check", "config": {"kind": "rule"}}
    refused = await client.post(f"{path}/rescore", json={"evaluators": wrong}, headers=session.headers)
    assert refused.status_code == 422
    assert "no_such_check" in refused.text

    await client.post(f"{path}/rescore", json={"evaluators": [edited(evaluation_steps=STEPS)]}, headers=session.headers)
    await jobs.drain()
    edited_version = (await shown_version(client, session, path))["id"]
    await client.post(f"{path}/rescore", json={}, headers=session.headers)
    await jobs.drain()
    assert (await shown_version(client, session, path))["id"] == edited_version


async def test_the_exact_request_the_judge_got_can_be_read_for_every_scoring_pass(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue
) -> None:
    _, path, answer = await setup(client, session, jobs)
    calls = (await client.get(f"{path}/answers/{answer}/judge-calls", headers=session.headers)).json()
    assert len(calls) == 2  # criteria: the judge writes its steps, then scores
    first_run = (await client.get(f"{path}/results", headers=session.headers)).json()["evaluation_run"]["id"]
    assert {c["evaluation_run_id"] for c in calls} == {first_run}
    assert {c["evaluator"] for c in calls} == {"g_eval_correctness"}
    assert not any(c["preview"] for c in calls)
    assert "The answer is a correct label." in sent(calls[0])
    assert calls[1]["output_text"]

    await client.post(f"{path}/rescore", json={"evaluators": [edited(evaluation_steps=STEPS)]}, headers=session.headers)
    await jobs.drain()
    after = (await client.get(f"{path}/answers/{answer}/judge-calls", headers=session.headers)).json()
    newest = [c for c in after if c["evaluation_run_id"] != first_run]
    assert len(newest) == 1  # steps given: the judge scores directly
    assert STEPS[0] in sent(newest[0])

    elsewhere = await client.get(
        f"{path}/answers/00000000-0000-0000-0000-000000000000/judge-calls", headers=session.headers
    )
    assert elsewhere.status_code == 200
    assert elsewhere.json() == []


async def test_trying_the_judge_shows_the_cost_first_records_the_call_and_changes_no_result(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, container: Container
) -> None:
    _, path, answer = await setup(client, session, jobs)
    before = (await client.get(f"{path}/results", headers=session.headers)).json()
    count = await versions(container)
    body = {"test_case_run_id": answer, "evaluator": edited(criteria="Is the label right?")}

    asked = await client.post(f"{path}/judge/try/estimate", json=body, headers=session.headers)
    assert asked.status_code == 200, asked.text
    assert asked.json()["judge_calls"] == 2
    assert asked.json()["judge_cost"] is not None
    assert asked.json()["judge_model"] == "scripted"
    assert len((await client.get(f"{path}/answers/{answer}/judge-calls", headers=session.headers)).json()) == 2

    tried = await client.post(f"{path}/judge/try", json=body, headers=session.headers)
    assert tried.status_code == 200, tried.text
    result = tried.json()
    assert result["score"]["status"] == "scored"
    assert result["score"]["reason"]
    assert len(result["calls"]) == 2
    assert all(call["preview"] for call in result["calls"])
    assert "Is the label right?" in sent(result["calls"][0])
    calls = (await client.get(f"{path}/answers/{answer}/judge-calls", headers=session.headers)).json()
    assert [c["preview"] for c in calls].count(True) == 2

    assert (await client.get(f"{path}/results", headers=session.headers)).json() == before
    assert await versions(container) == count


async def test_trying_a_check_that_cannot_run_says_why(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue
) -> None:
    _, path, answer = await setup(client, session, jobs)
    no_rubric = {"test_case_run_id": answer, "evaluator": edited(criteria="{rubric}")}
    refused = await client.post(f"{path}/judge/try", json=no_rubric, headers=session.headers)
    assert refused.status_code == 409
    assert "own rubric" in refused.text

    rule = copy.deepcopy(JUDGED)
    rule["config"] = {"kind": "rule"}
    not_judged = await client.post(
        f"{path}/judge/try", json={"test_case_run_id": answer, "evaluator": rule}, headers=session.headers
    )
    assert not_judged.status_code == 422

    missing = await client.post(
        f"{path}/judge/try",
        json={"test_case_run_id": "00000000-0000-0000-0000-000000000000", "evaluator": edited(criteria="x")},
        headers=session.headers,
    )
    assert missing.status_code == 404

    models = (await client.get(f"{base(session)}/models", params={"limit": 200}, headers=session.headers)).json()
    credential = models["items"][0]["credential_id"]
    down = await client.post(
        f"{path}/judge/try",
        json={
            "test_case_run_id": answer,
            "evaluator": edited(criteria="x"),
            "judge": {"credential_id": credential, "model": "judge_down"},
        },
        headers=session.headers,
    )
    assert down.status_code == 200, down.text
    assert down.json()["score"]["status"] == "unscored"
    assert down.json()["score"]["passed"] is False
