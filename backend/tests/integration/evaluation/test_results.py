"""
Integration tests for scoring and results on the mock provider: an experiment is scored
into an EvaluationRun with per-model metrics and a case view, exports as CSV, rescoring
adds a second run, and a G-Eval judge runs through the gateway as a recorded judge call.
"""

import csv
import io
from typing import Any

import httpx
import pytest
from sqlalchemy import select

from app.core.container import Container
from app.core.jobs import InlineJobQueue
from app.modules.evaluation.domain import EvalCase
from app.modules.evaluation.plugins.deepeval_adapter import judge
from app.modules.gateway.dependencies import build_gateway
from app.modules.gateway.models import LLMCall
from app.modules.gateway.schemas import CallContext
from app.modules.generator.schemas import TaskSpec
from app.modules.registry.service import RegistryService
from tests.helpers import Session, add_credential, approved_project

pytestmark = [pytest.mark.integration]


def url(session: Session, path: str) -> str:
    return f"/api/v1/projects/{session.project_id}/experiments{path}"


async def finished_experiment(client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue) -> dict[str, Any]:
    models = await approved_project(client, session, jobs)
    body = {"models": [{"model_profile_id": models["good"], "runs": 2}, {"model_profile_id": models["bad"], "runs": 2}]}
    response = await client.post(url(session, ""), json=body, headers=session.headers)
    await jobs.drain()
    experiment: dict[str, Any] = response.json()
    return experiment


async def test_an_experiment_is_scored_into_results_cases_and_csv(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue
) -> None:
    experiment = await finished_experiment(client, session, jobs)
    results = (await client.get(url(session, f"/{experiment['id']}/results"), headers=session.headers)).json()
    assert results["evaluation_run"]["trigger"] == "initial"
    by_model = {m["model"]: m for m in results["models"]}
    assert set(by_model) == {"good", "bad"}
    assert all(m["cases"] == 6 and 0 <= m["pass_rate"] <= 1 and m["consistency"] is not None for m in by_model.values())
    assert by_model["good"]["pass_rate"] >= by_model["bad"]["pass_rate"]

    cases = (await client.get(url(session, f"/{experiment['id']}/cases"), headers=session.headers)).json()
    assert len(cases) == 3
    outputs = cases[0]["outputs"]
    assert len(outputs) == 4
    assert {s["evaluator_name"] for s in outputs[0]["scores"]} >= {"exact_match", "allowed_values"}

    exported = await client.get(url(session, f"/{experiment['id']}/export.csv"), headers=session.headers)
    rows = list(csv.DictReader(io.StringIO(exported.text)))
    assert len(rows) == 12
    assert "exact_match" in rows[0]

    await client.post(url(session, f"/{experiment['id']}/rescore"), json={}, headers=session.headers)
    await jobs.drain()
    again = (await client.get(url(session, f"/{experiment['id']}/results"), headers=session.headers)).json()
    assert [r["trigger"] for r in again["evaluation_runs"]] == ["rescore", "initial"]


async def test_a_geval_judge_runs_through_the_gateway(
    client: httpx.AsyncClient, session: Session, container: Container
) -> None:
    credential = await add_credential(client, session, "mock")
    spec = TaskSpec(
        task_type="summarization", goal="Summarize tickets", input_variables=["ticket"], output_format="free_text"
    )
    case = EvalCase(
        inputs={"ticket": "My card was charged twice"},
        output="Double charge.",
        expected=None,
        rubric=None,
        task_spec=spec,
    )
    async with container.database.sessions() as db:
        registry = RegistryService(db, container)
        target = await registry.call_target(session.project_id, credential["id"], "scripted")
        await db.commit()
        result = await judge(
            build_gateway(container, registry),
            target,
            CallContext(project_id=session.project_id),
            "g_eval_faithfulness",
            {"kind": "deepeval", "criteria": "Nothing is invented."},
            0.5,
            case,
        )
        calls = list((await db.scalars(select(LLMCall).where(LLMCall.purpose == "judge"))).all())
    assert result is not None
    assert (result.value, result.passed) == (0.8, True)
    assert len(calls) == 2
