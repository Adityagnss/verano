"""
Integration tests for the logbook on the mock provider: one row per model answer read from the
existing run and score records, filters, sorting and paging, one answer beside the same case's
other answers, the analysis numbers agreeing with Results, the CSV, and the raw model calls.
"""

from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest

from app.core.jobs import InlineJobQueue
from tests.helpers import Session, approved_project

pytestmark = [pytest.mark.integration]


def getter(client: httpx.AsyncClient, session: Session, logbook: str) -> Callable[..., Awaitable[httpx.Response]]:
    async def get(path: str, **params: Any) -> httpx.Response:
        return await client.get(f"{logbook}{path}", params=params, headers=session.headers)

    return get


async def run_experiment(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue
) -> tuple[str, dict[str, Any]]:
    base = f"/api/v1/projects/{session.project_id}"
    models = await approved_project(client, session, jobs)
    body = {"models": [{"model_profile_id": models[name], "runs": 1} for name in ("echo", "scripted")]}
    experiment = (await client.post(f"{base}/experiments", json=body, headers=session.headers)).json()
    await jobs.drain()
    return f"{base}/logbook", experiment


async def test_the_logbook_lists_every_answer_and_filters_sorts_and_pages_them(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue
) -> None:
    logbook, experiment = await run_experiment(client, session, jobs)
    get = getter(client, session, logbook)

    options = (await get("/options")).json()
    assert [e["id"] for e in options["experiments"]] == [experiment["id"]]
    assert {"echo", "scripted"} <= set(options["models"])
    assert options["prompt_versions"][0]["version"] == 1

    response = await get("/answers")
    page = response.json()
    assert page["total"] == 6
    row = page["items"][0]
    assert row["prompt_version"] == 1
    assert row["source"] == "golden"
    assert row["input_preview"]
    assert {r["model"] for r in page["items"]} == {"echo", "scripted"}

    echo = (await get("/answers", models=["echo"])).json()
    assert echo["total"] == 3
    assert all(r["model"] == "echo" for r in echo["items"])
    assert (await get("/answers", models=["echo"], passed="true")).json()["total"] + (
        await get("/answers", models=["echo"], passed="false")
    ).json()["total"] == 3
    assert (await get("/answers", q="parcel")).json()["total"] == 2  # both models answered that case
    assert (await get("/answers", prompt_version_ids=[options["prompt_versions"][0]["id"]])).json()["total"] == 6
    assert (await get("/answers", statuses=["failed"])).json()["total"] == sum(
        r["status"] == "failed" for r in page["items"]
    )

    by_cost = (await get("/answers", sort="cost", order="asc")).json()["items"]
    costs = [r["cost"] for r in by_cost if r["cost"] is not None]
    assert costs == sorted(costs, key=float)
    second = (await get("/answers", offset=2, limit=2)).json()
    assert (second["offset"], len(second["items"]), second["total"]) == (2, 2, 6)
    assert (await get("/answers", limit=0)).status_code == 422


async def test_one_answer_is_shown_in_full_beside_the_other_models_on_the_same_case(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue
) -> None:
    logbook, experiment = await run_experiment(client, session, jobs)
    rows = (await client.get(f"{logbook}/answers", params={"models": ["echo"]}, headers=session.headers)).json()[
        "items"
    ]
    detail = (
        await client.get(f"{logbook}/answers/{experiment['id']}/{rows[0]['run_id']}", headers=session.headers)
    ).json()
    assert detail["row"]["run_id"] == rows[0]["run_id"]
    assert detail["golden_answer"]
    assert detail["rendered_user_prompt"]
    assert detail["scores"]
    assert [s["model"] for s in detail["siblings"]] == ["scripted"]
    missing = await client.get(f"{logbook}/answers/{experiment['id']}/{experiment['id']}", headers=session.headers)
    assert missing.status_code == 404


async def test_the_analysis_agrees_with_results_and_the_csv_and_calls_are_served(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue
) -> None:
    logbook, experiment = await run_experiment(client, session, jobs)
    base = f"/api/v1/projects/{session.project_id}"
    analysis = (await client.get(f"{logbook}/analysis", headers=session.headers)).json()
    results = (await client.get(f"{base}/experiments/{experiment['id']}/results", headers=session.headers)).json()
    assert analysis["totals"]["answers"] == 6
    assert analysis["totals"]["experiments"] == 1
    for model in results["models"]:
        group = next(g for g in analysis["groups"] if g["model"] == model["model"])
        assert group["pass_rate"] == pytest.approx(model["pass_rate"])
        assert group["quality"] == pytest.approx(model["quality"])
        assert group["failed_calls"] == model["failed_calls"]
    narrowed = (await client.get(f"{logbook}/analysis", params={"models": ["echo"]}, headers=session.headers)).json()
    assert [g["model"] for g in narrowed["groups"]] == ["echo"]

    export = await client.get(f"{logbook}/answers.csv", params={"models": ["echo"]}, headers=session.headers)
    assert export.headers["content-type"].startswith("text/csv")
    lines = export.text.strip().splitlines()
    assert lines[0].startswith("time,experiment,prompt_version,model")
    assert len(lines) == 1 + 3

    calls = (await client.get(f"{logbook}/calls", params={"purposes": ["test_run"]}, headers=session.headers)).json()
    assert calls["total"] >= 6
    assert all(c["purpose"] == "test_run" for c in calls["items"])
    call = (await client.get(f"{logbook}/calls/{calls['items'][0]['id']}", headers=session.headers)).json()
    assert call["request_messages"]
    assert call["row"]["experiment_id"] == experiment["id"]
    other = await client.get(f"{logbook}/calls", params={"q": "zzz-not-there"}, headers=session.headers)
    assert other.json()["total"] == 0
