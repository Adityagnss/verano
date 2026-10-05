"""
Integration tests for the experiment engine on the mock provider: every call planned once
and recorded completely, a failing call recorded without failing the run, the budget cap
stopping the run with finished results kept, and cancel skipping pending calls.
"""

import uuid
from typing import Any

import httpx
import pytest
from sqlalchemy import select

from app.core.container import Container
from app.core.jobs import InlineJobQueue
from app.modules.engine.models import TestCaseRun
from tests.helpers import Session, approved_project

pytestmark = [pytest.mark.integration]


def url(session: Session, path: str = "") -> str:
    return f"/api/v1/projects/{session.project_id}/experiments{path}"


async def start(client: httpx.AsyncClient, session: Session, body: dict[str, Any]) -> dict[str, Any]:
    response = await client.post(url(session), json=body, headers=session.headers)
    assert response.status_code == 201, response.text
    experiment: dict[str, Any] = response.json()
    return experiment


async def test_an_experiment_runs_every_call_once_and_records_it(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, container: Container
) -> None:
    models = await approved_project(client, session, jobs)
    body = {
        "models": [
            {"model_profile_id": models["good"], "runs": 2, "params": {"temperature": 0.2, "max_tokens": 10}},
            {"model_profile_id": models["rejected"], "runs": 1},
        ]
    }
    estimate = (await client.post(url(session, "/estimate"), json=body, headers=session.headers)).json()
    assert (estimate["cases"], estimate["calls"], estimate["price_known"]) == (3, 9, True)

    experiment = await start(client, session, body)
    await jobs.drain()
    done = (await client.get(url(session, f"/{experiment['id']}"), headers=session.headers)).json()
    assert done["status"] == "completed"
    progress = {p["model"]: (p["total"], p["succeeded"], p["failed"]) for p in done["progress"]}
    assert progress == {"good": (6, 6, 0), "rejected": (3, 0, 3)}
    async with container.database.sessions() as db:
        rows = list((await db.scalars(select(TestCaseRun).where(TestCaseRun.experiment_id == experiment["id"]))).all())
    ok = next(r for r in rows if r.status == "succeeded")
    recorded = [ok.rendered_system_prompt, ok.rendered_user_prompt, ok.raw_output, ok.input_tokens, ok.cost]
    assert all([*recorded, ok.llm_call_id, ok.trace_id, ok.completed_at])
    assert ok.params == {"temperature": 0.2, "max_tokens": 10}
    failed = next(r for r in rows if r.status == "failed")
    assert (failed.error_type, bool(failed.error_message)) == ("provider_bad_request", True)

    runs = done["estimate"]["models"]
    assert [m["calls"] for m in runs] == [6, 3]
    replay = await start(client, session, body)
    await jobs.drain()
    assert replay["id"] != experiment["id"]


async def test_the_budget_cap_stops_the_run_and_keeps_finished_results(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue
) -> None:
    models = await approved_project(client, session, jobs)
    body = {"models": [{"model_profile_id": models["good"], "runs": 5}], "budget_cap": "0.0000001"}
    experiment = await start(client, session, body)
    await jobs.drain()
    done = (await client.get(url(session, f"/{experiment['id']}"), headers=session.headers)).json()
    assert done["status"] == "cancelled"
    assert "Budget cap" in done["stop_reason"]
    progress = done["progress"][0]
    assert progress["succeeded"] >= 1
    assert progress["skipped"] >= 1
    assert progress["succeeded"] + progress["skipped"] + progress["failed"] == 15


async def test_cancel_skips_pending_calls(client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue) -> None:
    models = await approved_project(client, session, jobs)
    experiment = await start(client, session, {"models": [{"model_profile_id": models["echo"], "runs": 5}]})
    cancelled = await client.post(url(session, f"/{experiment['id']}/cancel"), headers=session.headers)
    await jobs.drain()
    assert cancelled.json()["status"] == "cancelled"
    done = (await client.get(url(session, f"/{experiment['id']}"), headers=session.headers)).json()
    progress = done["progress"][0]
    assert progress["skipped"] > 0
    assert progress["succeeded"] + progress["skipped"] == 15


async def test_settings_are_checked_when_the_experiment_is_created(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue
) -> None:
    models = await approved_project(client, session, jobs)
    good = models["good"]
    for params in ({"temprature": 0.2}, {"seed": "7"}, {"temperature": True}, {"stop": "END"}, {"top_p": 1.5}):
        body = {"models": [{"model_profile_id": good, "params": params}]}
        for path in ("", "/estimate"):
            response = await client.post(url(session, path), json=body, headers=session.headers)
            assert response.status_code == 422, (params, response.text)
    beyond = {"models": [{"model_profile_id": good, "params": {"max_tokens": 10**9}}]}
    refused = await client.post(url(session), json=beyond, headers=session.headers)
    assert refused.status_code == 422
    assert refused.json()["error"]["code"] == "invalid_parameter"


async def test_repeated_runs_use_the_next_seed_and_ignored_settings_are_recorded(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, container: Container
) -> None:
    models = await approved_project(client, session, jobs)
    params = {"temperature": 0, "seed": 42, "stop": ["END", "\n\n"]}
    body = {
        "models": [
            {"model_profile_id": models["good"], "runs": 3, "params": params},
            {"model_profile_id": models["scripted"], "runs": 1, "params": params},
        ]
    }
    experiment = await start(client, session, body)
    await jobs.drain()
    chosen = {m["display_name"]: m for m in experiment["config"]["models"]}
    assert chosen["good"]["params"] == {"temperature": 0.0, "seed": 42, "stop": ["\n\n", "END"]}
    assert chosen["good"]["ignored_params"] == []
    assert chosen["scripted"]["ignored_params"] == ["seed", "stop"]
    async with container.database.sessions() as db:
        rows = list((await db.scalars(select(TestCaseRun).where(TestCaseRun.experiment_id == experiment["id"]))).all())
    seeds = {run: {r.params["seed"] for r in rows if r.model == "good" and r.run_number == run} for run in (1, 2, 3)}
    assert seeds == {1: {42}, 2: {43}, 3: {44}}
    assert len({r.param_set_key for r in rows if r.model == "good"}) == 1


async def test_the_same_setup_has_the_same_configuration_hash_and_the_logbook_lists_it(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue
) -> None:
    models = await approved_project(client, session, jobs)

    def body(seed: int, name: str) -> dict[str, Any]:
        return {
            "name": name,
            "models": [{"model_profile_id": models["good"], "params": {"temperature": 0, "seed": seed}}],
        }

    first = await start(client, session, body(42, "First"))
    again = await start(client, session, {**body(42, "Second"), "budget_cap": "5"})
    other = await start(client, session, body(43, "Third"))
    await jobs.drain()
    hashes = {e["name"]: e["configuration"]["hash"] for e in (first, again, other)}
    assert hashes["First"] == hashes["Second"] != hashes["Third"]
    configuration = first["configuration"]
    assert [(m["display_name"], m["runs"], m["params"]) for m in configuration["models"]] == [
        ("good", 1, {"temperature": 0.0, "seed": 42})
    ]
    assert "litellm" in configuration["libraries"]

    options = await client.get(f"/api/v1/projects/{session.project_id}/logbook/options", headers=session.headers)
    assert options.status_code == 200, options.text
    listed = {e["name"]: e["config_hash"] for e in options.json()["experiments"]}
    assert listed == hashes


async def test_a_rerun_has_the_same_configuration_and_reproduces_the_answers_and_stability_is_reported(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue
) -> None:
    models = await approved_project(client, session, jobs)
    body = {"models": [{"model_profile_id": models["echo"], "runs": 3, "params": {"temperature": 0, "seed": 42}}]}
    original = await start(client, session, body)

    early = await client.post(url(session, f"/{original['id']}/rerun"), headers=session.headers)
    assert early.status_code == 409, early.text
    await jobs.drain()

    response = await client.post(url(session, f"/{original['id']}/rerun"), headers=session.headers)
    assert response.status_code == 201, response.text
    again = response.json()
    await jobs.drain()
    assert again["id"] != original["id"]
    assert again["name"].startswith("Re-run: ")
    assert again["configuration"]["hash"] == original["configuration"]["hash"]
    assert again["prompt_version_id"] == original["prompt_version_id"]
    assert again["total_calls"] == original["total_calls"] == 9

    results = (await client.get(url(session, f"/{original['id']}/results"), headers=session.headers)).json()
    (echo,) = results["models"]
    assert (echo["stability"], echo["stable_cases"], echo["compared_cases"]) == (1.0, 3, 3)
    cases = (await client.get(url(session, f"/{original['id']}/cases"), headers=session.headers)).json()
    assert all(c["agreement"] == [{"model_profile_id": models["echo"], "same": 3, "runs": 3}] for c in cases)

    check = await client.get(
        url(session, f"/{again['id']}/replication"), params={"against": original["id"]}, headers=session.headers
    )
    assert check.status_code == 200, check.text
    assert (check.json()["same"], check.json()["compared"], check.json()["skipped"]) == (9, 9, 0)
    assert check.json()["against_name"] == original["name"]


async def test_replication_is_only_for_finished_experiments_set_up_the_same_way(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue
) -> None:
    models = await approved_project(client, session, jobs)
    first = await start(client, session, {"models": [{"model_profile_id": models["echo"], "params": {"seed": 1}}]})
    second = await start(client, session, {"models": [{"model_profile_id": models["echo"], "params": {"seed": 2}}]})
    await jobs.drain()
    path = url(session, f"/{first['id']}/replication")
    different = await client.get(path, params={"against": second["id"]}, headers=session.headers)
    assert different.status_code == 409
    assert "same way" in different.json()["error"]["message"]
    itself = await client.get(path, params={"against": first["id"]}, headers=session.headers)
    assert itself.status_code == 409
    unknown = await client.get(path, params={"against": str(uuid.uuid4())}, headers=session.headers)
    assert unknown.status_code == 404
