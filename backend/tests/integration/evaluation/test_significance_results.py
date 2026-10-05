"""
Integration tests for the significance labels in Results: every model that is not the best on quality says how
it compares with the best (with the evidence), a lone model or the best one carries no label, a run too small
to tell says so, and a re-run is compared with its original by the same engine.
"""

from typing import Any

import httpx
import pytest

from app.core.jobs import InlineJobQueue
from tests.helpers import Session, approved_project, approved_project_with_cases, base, judged_project

pytestmark = [pytest.mark.integration]


async def run(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, models: dict[str, str], names: list[str]
) -> dict[str, Any]:
    body = {"models": [{"model_profile_id": models[name], "runs": 1} for name in names]}
    response = await client.post(f"{base(session)}/experiments", json=body, headers=session.headers)
    assert response.status_code == 201, response.text
    await jobs.drain()
    results = (
        await client.get(f"{base(session)}/experiments/{response.json()['id']}/results", headers=session.headers)
    ).json()
    return {"id": response.json()["id"], **{m["model"]: m for m in results["models"]}}


async def test_the_weaker_model_is_labelled_against_the_best_with_its_evidence(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue
) -> None:
    models = await approved_project_with_cases(client, session, jobs, count=40)
    found = await run(client, session, jobs, models, ["good", "bad"])
    best, weaker = found["good"], found["bad"]
    assert best["quality"] > weaker["quality"]
    assert best["vs_best"] is None
    compared = weaker["vs_best"]
    assert compared["label"] == "clear difference"
    assert compared["first_better"] is False
    assert compared["cases"] == 40
    assert compared["difference"] < 0
    assert compared["low"] < compared["high"] < 0
    assert compared["level"] == pytest.approx(0.95)
    assert compared["pass_rate_difference"] < 0
    assert compared["second_only_passed"] > compared["first_only_passed"]
    assert "95% interval" in compared["method"]


async def test_a_run_with_too_few_cases_says_so_instead_of_claiming_a_difference(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue
) -> None:
    models = await approved_project(client, session, jobs)
    found = await run(client, session, jobs, models, ["good", "bad"])
    labelled = [m for m in (found["good"], found["bad"]) if m["vs_best"] is not None]
    assert len(labelled) == 1
    assert labelled[0]["vs_best"]["label"] == "too few cases"
    assert labelled[0]["vs_best"]["low"] is None
    assert labelled[0]["vs_best"]["cases"] == 3


async def test_one_model_alone_has_nothing_to_be_compared_with(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue
) -> None:
    models = await approved_project(client, session, jobs)
    found = await run(client, session, jobs, models, ["good"])
    assert found["good"]["vs_best"] is None


async def test_a_rerun_is_compared_with_its_original_by_the_same_engine(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue
) -> None:
    models = await approved_project_with_cases(client, session, jobs, count=40)
    first = await run(client, session, jobs, models, ["good"])
    again = await client.post(f"{base(session)}/experiments/{first['id']}/rerun", headers=session.headers)
    assert again.status_code == 201, again.text
    await jobs.drain()
    checked = await client.get(
        f"{base(session)}/experiments/{again.json()['id']}/replication",
        params={"against": first["id"]},
        headers=session.headers,
    )
    assert checked.status_code == 200, checked.text
    quality = checked.json()["models"][0]["quality"]
    assert quality["cases"] == 40
    assert quality["label"] == "no clear difference"
    assert quality["difference"] == pytest.approx(0.0)


async def test_runs_scored_with_different_judges_are_not_compared_on_quality(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue
) -> None:
    models = await judged_project(client, session, jobs, set_judge="scripted")
    first = await run(client, session, jobs, models, ["good"])
    again = await client.post(f"{base(session)}/experiments/{first['id']}/rerun", headers=session.headers)
    await jobs.drain()
    path = f"{base(session)}/experiments/{again.json()['id']}"
    ask = {"against": first["id"]}
    same_judge = (await client.get(f"{path}/replication", params=ask, headers=session.headers)).json()
    assert same_judge["models"][0]["quality"] is not None

    other = {"judge": {"credential_id": models["_credential"], "model": "echo"}}
    assert (await client.post(f"{path}/rescore", json=other, headers=session.headers)).status_code == 202
    await jobs.drain()
    other_judge = (await client.get(f"{path}/replication", params=ask, headers=session.headers)).json()
    assert other_judge["models"][0]["quality"] is None
