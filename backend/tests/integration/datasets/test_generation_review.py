"""
Integration tests for the Eval Generator and Review & Approve on mock/scripted: Task Spec
draft and confirmation, gap-filling generation grounded in a document, dedupe, label
balance, drafted answers that never touch golden rows, evaluator selection, mandatory
review, the stratified 70/30 split, the frozen version, and "Use only my golden set".
Also the safety limits: cancel, the generation budget cap and the cost confirmation.
"""

from decimal import Decimal
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select

from app.core.container import Container
from app.core.jobs import InlineJobQueue
from app.modules.gateway.models import LLMCall
from tests.files import rows_file
from tests.helpers import Session, add_credential, add_golden, add_input_files, create_prompt, upload

pytestmark = [pytest.mark.integration, pytest.mark.datasets]

GOLDEN = [
    {"ticket": "My card was charged twice", "expected": "billing"},
    {"ticket": "Where is my parcel?", "expected": "shipping"},
    {"ticket": "The app crashes on start", "expected": "technical"},
]
DOCUMENT = b"Refund policy\n\nRefunds are issued within 5 business days to the original payment method."


def api(session: Session, path: str) -> str:
    return f"/api/v1/projects/{session.project_id}{path}"


async def ingest(client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, rows: list[dict[str, Any]]) -> None:
    """Each row is an input file (its ticket text) with a golden answer."""
    await add_input_files(client, session, jobs, [row["ticket"] for row in rows])
    content = rows_file([{"expected": row["expected"]} for row in rows], "csv")
    await add_golden(client, session, jobs, "golden.csv", content, {"expected_output": "expected"})


async def confirmed_spec(client: httpx.AsyncClient, session: Session, version_id: str) -> str:
    credential = await add_credential(client, session, "mock")
    body = {"prompt_version_id": version_id, "credential_id": credential["id"], "model": "scripted"}
    drafted = await client.post(api(session, "/task-specs"), json=body, headers=session.headers)
    assert drafted.status_code == 201, drafted.text
    spec = drafted.json()
    assert spec["status"] == "draft"
    assert spec["spec"]["input_variables"] == ["ticket"]
    early = await client.post(api(session, "/generations"), json={"task_spec_id": spec["id"]}, headers=session.headers)
    assert early.status_code == 409
    confirmed = await client.put(
        api(session, f"/task-specs/{spec['id']}"), json={"spec": spec["spec"]}, headers=session.headers
    )
    assert confirmed.json()["status"] == "confirmed"
    return str(spec["id"])


async def items(client: httpx.AsyncClient, session: Session, version_id: str, **where: str) -> list[dict[str, Any]]:
    response = await client.get(
        api(session, f"/dataset-versions/{version_id}/items"),
        params={"limit": 200, **where},
        headers=session.headers,
    )
    assert response.status_code == 200, response.text
    found: list[dict[str, Any]] = response.json()["items"]
    return found


async def test_generate_review_and_approve(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, container: Container
) -> None:
    prompt = await create_prompt(client, session)
    await ingest(client, session, jobs, GOLDEN)
    await upload(client, session, "policy.txt", DOCUMENT, purpose="document")
    await jobs.drain()
    spec_id = await confirmed_spec(client, session, prompt["id"])

    request = {"task_spec_id": spec_id, "target_size": 20}
    estimate = (await client.post(api(session, "/generations/estimate"), json=request, headers=session.headers)).json()
    assert (estimate["cases_to_generate"], estimate["answers_to_draft"], estimate["price_known"]) == (17, 17, True)
    started = await client.post(api(session, "/generations"), json=request, headers=session.headers)
    assert started.status_code == 202, started.text
    version_id = started.json()["id"]
    await jobs.drain()

    version = (await client.get(api(session, f"/dataset-versions/{version_id}"), headers=session.headers)).json()
    assert version["generation"]["status"] == "succeeded", version["generation"]
    assert version["generation"]["dropped_duplicates"] >= 1
    categories = {name: group["total"] for name, group in version["by_category"].items()}
    assert categories == {"happy_path": 4 + 4 + 2, "edge_case": 5, "tricky": 3, "format_stress": 2, "adversarial": 2}

    golden = await items(client, session, version_id, source="golden")
    assert [(i["expected_output"], i["review_status"]) for i in golden] == [
        ("billing", "trusted"),
        ("shipping", "trusted"),
        ("technical", "trusted"),
    ]
    drafts = await items(client, session, version_id, review_status="draft")
    assert all(i["source"] in {"input_file", "generated"} for i in drafts)
    assert all(i["context"] for i in drafts if i["category"] == "edge_case")
    assert {i["expected_output"] for i in drafts if i["inputs"]["ticket"].startswith(("Do you", "Can I suggest"))} == {
        "other"
    }

    evaluators = (
        await client.get(api(session, f"/dataset-versions/{version_id}/evaluators"), headers=session.headers)
    ).json()
    assert [e["evaluator_name"] for e in evaluators["evaluators"]] == ["exact_match", "allowed_values", "constraints"]

    blocked = await client.post(api(session, f"/dataset-versions/{version_id}/approve"), headers=session.headers)
    assert blocked.status_code == 422
    assert "need review" in blocked.json()["error"]["message"]

    edited = await client.patch(
        api(session, f"/dataset-versions/{version_id}/items/{drafts[0]['id']}"),
        json={"expected_output": "billing"},
        headers=session.headers,
    )
    assert edited.json()["review_status"] == "approved"
    for category in categories:
        response = await client.post(
            api(session, f"/dataset-versions/{version_id}/approve-drafts"),
            json={"category": category},
            headers=session.headers,
        )
        assert response.status_code == 200
    unanswered = [i for i in await items(client, session, version_id) if not i["expected_output"] and not i["rubric"]]
    for item in unanswered:
        await client.delete(api(session, f"/dataset-versions/{version_id}/items/{item['id']}"), headers=session.headers)

    approved = await client.post(api(session, f"/dataset-versions/{version_id}/approve"), headers=session.headers)
    assert approved.status_code == 200, approved.text
    summary = approved.json()
    assert summary["status"] == "approved"
    assert summary["by_split"]["holdout"] == round(summary["item_count"] * 0.3)
    assert any("holdout will have" in warning for warning in summary["warnings"])
    holdout = await items(client, session, version_id, split="holdout")
    assert any(i["source"] == "golden" for i in holdout)

    frozen = await client.patch(
        api(session, f"/dataset-versions/{version_id}/items/{golden[0]['id']}"),
        json={"expected_output": "shipping"},
        headers=session.headers,
    )
    assert frozen.status_code == 409


async def test_golden_only_makes_no_generation_calls(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, container: Container
) -> None:
    prompt = await create_prompt(client, session)
    await ingest(client, session, jobs, GOLDEN)
    spec_id = await confirmed_spec(client, session, prompt["id"])
    async with container.database.sessions() as db:
        calls_before = await db.scalar(select(func.count()).select_from(LLMCall))

    started = await client.post(
        api(session, "/generations"), json={"task_spec_id": spec_id, "golden_only": True}, headers=session.headers
    )
    version_id = started.json()["id"]
    await jobs.drain()

    async with container.database.sessions() as db:
        assert await db.scalar(select(func.count()).select_from(LLMCall)) == calls_before
    version = (await client.get(api(session, f"/dataset-versions/{version_id}"), headers=session.headers)).json()
    assert version["generation"]["status"] == "succeeded"
    assert version["by_source"] == {"golden": {"total": 3, "draft": 0, "without_answer": 0}}
    approved = await client.post(api(session, f"/dataset-versions/{version_id}/approve"), headers=session.headers)
    assert approved.status_code == 200, approved.text


async def generation_state(client: httpx.AsyncClient, session: Session, version_id: str) -> dict[str, Any]:
    version = (await client.get(api(session, f"/dataset-versions/{version_id}"), headers=session.headers)).json()
    state: dict[str, Any] = version["generation"]
    return state


async def test_cancel_stops_before_the_next_model_call(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue
) -> None:
    prompt = await create_prompt(client, session)
    await ingest(client, session, jobs, GOLDEN)
    spec_id = await confirmed_spec(client, session, prompt["id"])
    started = await client.post(
        api(session, "/generations"), json={"task_spec_id": spec_id, "target_size": 20}, headers=session.headers
    )
    version_id = started.json()["id"]
    second = await client.post(
        api(session, "/generations"), json={"task_spec_id": spec_id, "target_size": 20}, headers=session.headers
    )
    assert second.status_code == 409

    cancel = api(session, f"/dataset-versions/{version_id}/generation/cancel")
    assert (await client.post(cancel, headers=session.headers)).status_code == 200
    await jobs.drain()

    state = await generation_state(client, session, version_id)
    assert state["status"] == "stopped"
    assert "your request" in state["message"]
    assert (await client.post(cancel, headers=session.headers)).status_code == 409
    assert len(await items(client, session, version_id, source="golden")) == 3


async def test_budget_cap_stops_generation_and_keeps_the_cases(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue
) -> None:
    prompt = await create_prompt(client, session)
    await ingest(client, session, jobs, GOLDEN)
    spec_id = await confirmed_spec(client, session, prompt["id"])
    request = {"task_spec_id": spec_id, "target_size": 20, "budget_cap": "0.000000001"}
    started = await client.post(api(session, "/generations"), json=request, headers=session.headers)
    version_id = started.json()["id"]
    await jobs.drain()

    state = await generation_state(client, session, version_id)
    assert state["status"] == "stopped"
    assert "budget" in state["message"]
    assert float(state["spent"]) >= 1e-9
    generated = await items(client, session, version_id, source="generated")
    assert 0 < len(generated) < 17


async def test_a_costly_run_needs_the_cost_confirmed(
    client: httpx.AsyncClient,
    session: Session,
    jobs: InlineJobQueue,
    container: Container,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prompt = await create_prompt(client, session)
    await ingest(client, session, jobs, GOLDEN)
    spec_id = await confirmed_spec(client, session, prompt["id"])
    monkeypatch.setattr(container.settings, "generator_confirm_cost", Decimal("0.000000001"))
    request = {"task_spec_id": spec_id, "target_size": 20}

    estimate = (await client.post(api(session, "/generations/estimate"), json=request, headers=session.headers)).json()
    assert estimate["needs_confirmation"] is True
    refused = await client.post(api(session, "/generations"), json=request, headers=session.headers)
    assert refused.status_code == 409
    assert "Confirm the cost" in refused.json()["error"]["message"]
    accepted = await client.post(
        api(session, "/generations"), json={**request, "accept_cost": True}, headers=session.headers
    )
    assert accepted.status_code == 202, accepted.text
    await jobs.drain()
