"""
Integration tests for a judge that cannot score: the answer is shown as unscored with the reason,
never as a pass or a zero, in Results, the case view, the CSV and the Logbook; and an experiment
whose checks need a judge is refused when none is chosen.
"""

import csv
import io

import httpx
import pytest
from sqlalchemy import select

from app.core.container import Container
from app.core.jobs import InlineJobQueue
from app.modules.evaluation.models import Score
from tests.helpers import JUDGED, Session, base, judged_project, run_good

pytestmark = [pytest.mark.integration]


async def test_a_judge_that_fails_leaves_every_answer_unscored_never_passed(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, container: Container
) -> None:
    models = await judged_project(client, session, jobs, spec_judge="judge_down")
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
    models = await judged_project(client, session, jobs, spec_judge="scripted")
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
    models = await judged_project(client, session, jobs, spec_judge=None)
    body = {"models": [{"model_profile_id": models["good"]}]}
    for path in ("/experiments/estimate", "/experiments"):
        refused = await client.post(f"{base(session)}{path}", json=body, headers=session.headers)
        assert refused.status_code == 422, path
        assert "no judge model is chosen" in refused.json()["error"]["message"]
