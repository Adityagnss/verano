"""
Integration tests for a judge that cannot score: the answer is shown as unscored with the reason,
never as a pass or a zero, in Results, the case view, the CSV and the Logbook; and an experiment
whose checks need a judge is refused when none is chosen.
"""

import csv
import io
import uuid

import httpx
import pytest
from sqlalchemy import select

from app.core.container import Container
from app.core.jobs import InlineJobQueue
from app.modules.evaluation.models import EvaluationRun, Score
from app.modules.evaluation.schemas import EvaluationTrigger
from app.modules.evaluation.scoring import ScoringService
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


async def runs_of(container: Container, experiment_id: str) -> list[tuple[str, str]]:
    async with container.database.sessions() as db:
        rows = (
            await db.scalars(select(EvaluationRun).where(EvaluationRun.experiment_id == uuid.UUID(experiment_id)))
        ).all()
        return sorted((r.trigger.value, r.status.value) for r in rows)


async def test_a_rescore_is_visible_as_pending_at_once_and_a_redelivered_job_scores_once(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, container: Container
) -> None:
    models = await judged_project(client, session, jobs, set_judge="scripted")
    experiment = await run_good(client, session, jobs, models)
    path = f"{base(session)}/experiments/{experiment['id']}"

    accepted = await client.post(f"{path}/rescore", json={}, headers=session.headers)
    assert accepted.status_code == 202
    shown = accepted.json()["evaluation_runs"]
    assert [(r["trigger"], r["status"]) for r in shown] == [("rescore", "pending"), ("initial", "completed")]
    assert accepted.json()["evaluation_run"]["trigger"] == "initial"  # results still show the finished pass

    await jobs.drain()
    assert await runs_of(container, experiment["id"]) == [("initial", "completed"), ("rescore", "completed")]
    again = next(r for r in (await client.get(f"{path}/results", headers=session.headers)).json()["evaluation_runs"])
    async with container.database.sessions() as db:
        redelivered = await ScoringService(db, container).score(
            uuid.UUID(experiment["id"]), EvaluationTrigger.RESCORE, None, uuid.UUID(again["id"])
        )
    assert redelivered is None
    assert await runs_of(container, experiment["id"]) == [("initial", "completed"), ("rescore", "completed")]


async def test_a_scoring_pass_that_crashes_is_marked_failed_and_the_earlier_results_stay(
    client: httpx.AsyncClient,
    session: Session,
    jobs: InlineJobQueue,
    container: Container,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    models = await judged_project(client, session, jobs, set_judge="scripted")
    experiment = await run_good(client, session, jobs, models)
    path = f"{base(session)}/experiments/{experiment['id']}"

    async def crash(*_: object, **__: object) -> None:
        raise RuntimeError("the scorer fell over")

    monkeypatch.setattr(ScoringService, "_score_pass", crash)
    await client.post(f"{path}/rescore", json={}, headers=session.headers)
    with pytest.raises(RuntimeError, match="fell over"):
        await jobs.drain()
    assert await runs_of(container, experiment["id"]) == [("initial", "completed"), ("rescore", "failed")]
    results = (await client.get(f"{path}/results", headers=session.headers)).json()
    assert results["evaluation_run"]["trigger"] == "initial"
    assert results["models"][0]["judged_cases"] == 6
