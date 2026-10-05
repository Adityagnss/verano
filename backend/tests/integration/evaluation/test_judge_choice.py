"""
Integration tests for choosing the judge: it lives on the evaluator-set version, can be chosen when a run
starts or when scoring again (always as a version of its own, never by touching the frozen dataset), is
reused rather than piled up, costs nothing to ask about, and is never mixed with another judge's scores.
"""

from typing import Any

import httpx
import pytest
from sqlalchemy import func, select

from app.core.container import Container
from app.core.jobs import InlineJobQueue
from app.modules.evaluation.models import EvaluatorSetVersion
from tests.helpers import Session, base, judged_project, run_good

pytestmark = [pytest.mark.integration]


async def version_count(container: Container) -> int:
    async with container.database.sessions() as db:
        return int(await db.scalar(select(func.count()).select_from(EvaluatorSetVersion)) or 0)


def judge_of(models: dict[str, str], name: str) -> dict[str, str]:
    return {"credential_id": models["_credential"], "model": name}


async def test_a_judge_on_the_evaluator_set_version_wins_over_the_old_generator_fallback(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue
) -> None:
    models = await judged_project(client, session, jobs, spec_judge="judge_down", set_judge="scripted")
    evaluators = (
        await client.get(
            f"{base(session)}/dataset-versions/{models['_dataset_version']}/evaluators", headers=session.headers
        )
    ).json()
    assert evaluators["judge"]["model"] == "scripted"
    experiment = await run_good(client, session, jobs, models)
    assert experiment["config"]["judge"]["model"] == "scripted"
    assert experiment["config"]["judge"]["source"] == "evaluator_set"
    results = (
        await client.get(f"{base(session)}/experiments/{experiment['id']}/results", headers=session.headers)
    ).json()
    assert (results["models"][0]["judged_cases"], results["models"][0]["unscored_cases"]) == (6, 0)


async def test_a_judge_chosen_for_a_run_is_a_version_of_its_own_and_is_reused(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, container: Container
) -> None:
    models = await judged_project(client, session, jobs, set_judge="scripted")
    original = models["_evaluator_set_version"]
    chosen = {"judge": judge_of(models, "echo")}
    before = await version_count(container)
    for path in ("/experiments/estimate",):
        asked = await client.post(
            f"{base(session)}{path}",
            json={"models": [{"model_profile_id": models["good"]}], **chosen},
            headers=session.headers,
        )
        assert asked.status_code == 200, asked.text
    assert await version_count(container) == before

    first = await run_good(client, session, jobs, models, **chosen)
    assert first["evaluator_set_version_id"] != original
    assert first["config"]["judge"] == {**chosen["judge"], "source": "run"}
    assert await version_count(container) == before + 1
    again = await run_good(client, session, jobs, models, **chosen)
    assert again["evaluator_set_version_id"] == first["evaluator_set_version_id"]
    assert await version_count(container) == before + 1
    other = await run_good(client, session, jobs, models, judge=judge_of(models, "bad"))
    assert other["evaluator_set_version_id"] not in {original, first["evaluator_set_version_id"]}
    same_as_stored = await run_good(client, session, jobs, models, judge=judge_of(models, "scripted"))
    assert same_as_stored["evaluator_set_version_id"] == original

    rerun = await client.post(f"{base(session)}/experiments/{first['id']}/rerun", headers=session.headers)
    assert rerun.status_code == 201, rerun.text
    await jobs.drain()
    assert rerun.json()["evaluator_set_version_id"] == first["evaluator_set_version_id"]
    assert rerun.json()["configuration"]["hash"] == first["configuration"]["hash"]


async def test_a_judge_that_is_not_one_of_your_models_or_a_version_from_elsewhere_is_refused(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue
) -> None:
    models = await judged_project(client, session, jobs, spec_judge="scripted")
    body = {"models": [{"model_profile_id": models["good"]}]}
    for path in ("/experiments/estimate", "/experiments"):
        unknown = await client.post(
            f"{base(session)}{path}", json={**body, "judge": judge_of(models, "no-such-model")}, headers=session.headers
        )
        assert unknown.status_code == 404, path
        elsewhere = await client.post(
            f"{base(session)}{path}",
            json={**body, "evaluator_set_version_id": "00000000-0000-7000-8000-000000000000"},
            headers=session.headers,
        )
        assert elsewhere.status_code == 404, path


async def test_scoring_again_with_another_judge_is_a_separate_pass_and_the_first_stays_readable(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, container: Container
) -> None:
    models = await judged_project(client, session, jobs, set_judge="scripted")
    experiment = await run_good(client, session, jobs, models)
    path = f"{base(session)}/experiments/{experiment['id']}"
    first = (await client.get(f"{path}/results", headers=session.headers)).json()
    first_run = first["evaluation_run"]

    count = await version_count(container)
    body = {"judge": judge_of(models, "judge_down")}
    asked = await client.post(f"{path}/rescore/estimate", json=body, headers=session.headers)
    assert asked.status_code == 200, asked.text
    assert (asked.json()["judge_calls"], asked.json()["judge_model"]) == (
        12,
        "judge_down",
    )  # criteria: one call writes the steps, one scores
    assert asked.json()["judge_cost"] is not None
    assert await version_count(container) == count

    accepted = await client.post(f"{path}/rescore", json=body, headers=session.headers)
    assert accepted.status_code == 202, accepted.text
    await jobs.drain()
    second = (await client.get(f"{path}/results", headers=session.headers)).json()
    runs = second["evaluation_runs"]
    assert [r["trigger"] for r in runs] == ["rescore", "initial"]
    assert runs[0]["evaluator_set_version_id"] != runs[1]["evaluator_set_version_id"]
    assert (second["models"][0]["judged_cases"], second["models"][0]["unscored_cases"]) == (0, 6)
    old = (
        await client.get(f"{path}/results", params={"evaluation_run_id": first_run["id"]}, headers=session.headers)
    ).json()
    assert (old["models"][0]["judged_cases"], old["models"][0]["unscored_cases"]) == (6, 0)

    version = (
        await client.get(
            f"{base(session)}/evaluator-set-versions/{runs[0]['evaluator_set_version_id']}", headers=session.headers
        )
    ).json()
    assert version["judge"]["model"] == "judge_down"
    assert "Judge changed to judge_down" in version["change_reason"]
    await client.post(f"{path}/rescore", json=body, headers=session.headers)
    await jobs.drain()
    third = (await client.get(f"{path}/results", headers=session.headers)).json()
    assert len({r["evaluator_set_version_id"] for r in third["evaluation_runs"]}) == 2
    assert await version_count(container) == count + 1

    missing = await client.post(
        f"{path}/rescore/estimate", json={"judge": judge_of(models, "no-such-model")}, headers=session.headers
    )
    assert missing.status_code == 404


async def test_the_judge_suggestion_is_the_priciest_model_that_is_not_being_tested(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue
) -> None:
    models = await judged_project(client, session, jobs, spec_judge="scripted")
    selected = await client.put(
        f"{base(session)}/models/selection", json={"selected": [models["good"]]}, headers=session.headers
    )
    assert selected.status_code == 204
    listed = (await client.get(f"{base(session)}/models", params={"limit": 200}, headers=session.headers)).json()[
        "items"
    ]
    free = [m for m in listed if not m["is_selected"] and m["output_price_per_mtok"] is not None]
    best = max(free, key=lambda m: float(m["output_price_per_mtok"]))
    suggestion = (await client.get(f"{base(session)}/judge/suggestion", headers=session.headers)).json()
    assert suggestion["suggested"]["model"] == best["model_name"]
    assert "not being tested" in suggestion["reason"]
    assert len(suggestion["candidates"]) == len(listed)
    every_model: list[dict[str, Any]] = [{"selected": [m["id"] for m in listed]}]
    await client.put(f"{base(session)}/models/selection", json=every_model[0], headers=session.headers)
    everyone = (await client.get(f"{base(session)}/judge/suggestion", headers=session.headers)).json()
    assert "also being tested" in everyone["reason"]
