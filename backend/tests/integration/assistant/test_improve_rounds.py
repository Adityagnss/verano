"""
Integration tests for multi-round Improve (S9.5, ADR 0036) on the mock provider, using models whose answers depend on
the prompt (`tests/mock_behaviors.py`): a proven round winner starts the next round, an unproven one ends the session
as "not proven", the last winner is compared with the very first prompt, drafts that could not be tested are stored
with the reason, the quick check tests a small fixed sample and drops the weak, and the sizing says how many cases a
goal needs.
"""

from typing import Any

import httpx
import pytest

from app.core.container import Container
from app.core.jobs import InlineJobQueue
from tests.helpers import Session, approved_project_with_cases

pytestmark = [pytest.mark.integration]


def base(session: Session) -> str:
    return f"/api/v1/projects/{session.project_id}"


async def baseline_run(client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, model: str) -> dict[str, Any]:
    models = await approved_project_with_cases(client, session, jobs, count=40)
    body = {"models": [{"model_profile_id": models[model], "runs": 1}]}
    started = await client.post(f"{base(session)}/experiments", json=body, headers=session.headers)
    assert started.status_code == 201, started.text
    await jobs.drain()
    experiment: dict[str, Any] = started.json()
    return experiment


async def improve(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, experiment_id: str, **options: Any
) -> dict[str, Any]:
    body = {"experiment_id": experiment_id, **options}
    started = await client.post(f"{base(session)}/improvements", json=body, headers=session.headers)
    assert started.status_code == 202, started.text
    await jobs.drain()
    latest = await client.get(
        f"{base(session)}/improvements/latest", params={"experiment_id": experiment_id}, headers=session.headers
    )
    result: dict[str, Any] = latest.json()
    return result


@pytest.fixture(autouse=True)
def enough_holdout(container: Container, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(container.settings, "dataset_min_holdout", 10)


async def test_two_proven_rounds_build_a_tree_and_the_final_winner_beats_the_first_prompt(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue
) -> None:
    experiment = await baseline_run(client, session, jobs, "sensitive")
    result = await improve(client, session, jobs, experiment["id"], rounds=3, population=3, quick_check=False)

    assert result["stage"] == "done"
    assert (result["round_limit"], result["population"], result["quick_check"]) == (3, 3, False)
    rounds = result["rounds"]
    assert [(r["round"], r["proven"]) for r in rounds] == [(1, True), (2, True)]
    assert all(r["label"] == "Proven on held-back cases" for r in rounds)
    assert result["current_round"] == 3  # round 3 found no failure left, so the search finished there
    assert "no failures left" in result["message"]
    by_id = {c["id"]: c for c in result["candidates"]}
    second = by_id[rounds[1]["winner_candidate_id"]]
    first = by_id[rounds[0]["winner_candidate_id"]]
    assert second["parent_candidate_id"] == first["id"]  # round two grew from the proven round-one winner
    assert first["parent_candidate_id"] is None
    assert result["final_candidate_id"] == second["id"]
    assert result["versus_first"]["reason"] == "proven"  # the last winner against the very first prompt
    assert second["holdout_quality"] > first["holdout_quality"] > result["baseline_holdout_quality"]
    assert second["metrics"]["front"] == 0
    assert result["sizing"]["needed_cases"] >= 2 and result["sizing"]["holdout_cases"] == 12
    assert "held-back cases" in result["sizing"]["message"]

    accepted = await client.post(
        f"{base(session)}/improvements/{result['id']}/candidates/{second['id']}/accept", headers=session.headers
    )
    assert accepted.status_code == 200, accepted.text


async def test_an_unproven_round_ends_the_session_and_keeps_the_last_proven_winner(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue
) -> None:
    experiment = await baseline_run(client, session, jobs, "sensitive_flat")
    result = await improve(client, session, jobs, experiment["id"], rounds=3, population=3, quick_check=False)

    assert result["stage"] == "done"
    rounds = result["rounds"]
    assert [(r["round"], r["proven"]) for r in rounds] == [(1, True), (2, False)]
    assert rounds[1]["label"].startswith("Not proven")
    assert result["current_round"] == 2  # no third round was built on a result that was not proven
    assert result["message"].startswith("Round 2 was not proven, so the search stopped")
    winners = {r["round"]: r["winner_candidate_id"] for r in rounds}
    assert result["final_candidate_id"] == winners[1]  # the answer is the last PROVEN winner
    by_id = {c["id"]: c for c in result["candidates"]}
    assert by_id[winners[2]]["outcome"] == "not_better"
    assert by_id[winners[1]]["outcome"] == "better"


async def test_a_session_that_never_proves_anything_says_not_proven_after_one_round(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue
) -> None:
    experiment = await baseline_run(client, session, jobs, "echo")
    result = await improve(client, session, jobs, experiment["id"], rounds=3, population=3, quick_check=False)
    assert result["stage"] == "done"
    assert [(r["round"], r["proven"]) for r in result["rounds"]] == [(1, False)]
    assert result["rounds"][0]["label"].startswith("Not proven")
    assert result["final_candidate_id"] is None
    assert result["current_round"] == 1


async def test_the_quick_check_tests_a_small_fixed_sample_and_only_survivors_get_the_full_test(
    client: httpx.AsyncClient,
    session: Session,
    jobs: InlineJobQueue,
    container: Container,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(container.settings, "improve_quick_min_cases", 10)
    monkeypatch.setattr(container.settings, "improve_quick_max_cases", 10)
    experiment = await baseline_run(client, session, jobs, "sensitive")
    result = await improve(client, session, jobs, experiment["id"], rounds=1, population=3, quick_check=True)

    assert result["stage"] == "done"
    assert result["sizing"]["quick_sample"] == 10
    candidates = result["candidates"]
    quick = [c for c in candidates if c["quick_experiment_id"]]
    assert len(quick) == 3
    full = [c for c in candidates if c["optimize_experiment_id"]]
    assert len(full) == container.settings.improve_survivors  # only the best two got the full test
    dropped = [c for c in candidates if not c["optimize_experiment_id"]]
    assert len(dropped) == 1
    assert dropped[0]["outcome"] == "not_better"
    assert dropped[0]["rejection_reason"].startswith("Dropped at the quick check")
    assert dropped[0]["quick_quality"] is not None

    sample_runs = []
    for candidate in quick:
        shown = (
            await client.get(f"{base(session)}/experiments/{candidate['quick_experiment_id']}", headers=session.headers)
        ).json()
        sample_runs.append(shown["progress"][0]["total"])
    assert sample_runs == [10, 10, 10]  # every candidate saw the same number of cases


async def test_a_draft_that_changes_the_inputs_is_kept_as_rejected_with_the_reason(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue
) -> None:
    experiment = await baseline_run(client, session, jobs, "echo")
    result = await improve(client, session, jobs, experiment["id"], rounds=1, population=3, quick_check=False)
    # the generic fixture proposes system-only prompts: all are testable; a test that cannot run is stored with why
    assert all(c["outcome"] != "rejected" for c in result["candidates"])
    assert all(c["system_template"] for c in result["candidates"])
