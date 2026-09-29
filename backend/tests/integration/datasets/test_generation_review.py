"""
Integration tests for the Eval Generator and Review & Approve on mock/scripted: Task Spec
draft and confirmation, gap-filling generation grounded in a document, dedupe, label
balance, drafted answers that never touch golden rows, evaluator selection, mandatory
review, the stratified 70/30 split, the frozen version, and "Use only my golden set".
"""

from typing import Any

import httpx
import pytest
from sqlalchemy import func, select

from app.core.container import Container
from app.core.jobs import InlineJobQueue
from app.modules.gateway.models import LLMCall
from tests.files import rows_file
from tests.helpers import Session, add_credential, create_prompt, import_file, map_file, upload

pytestmark = [pytest.mark.integration, pytest.mark.datasets]

GOLDEN = [
    {"ticket": "My card was charged twice", "expected": "billing"},
    {"ticket": "Where is my parcel?", "expected": "shipping"},
    {"ticket": "The app crashes on start", "expected": "technical"},
]
DOCUMENT = b"Refund policy\n\nRefunds are issued within 5 business days to the original payment method."


def api(session: Session, path: str) -> str:
    return f"/api/v1/projects/{session.project_id}{path}"


async def ingest(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, version_id: str, rows: list[dict[str, Any]]
) -> None:
    response = await upload(client, session, "rows.csv", rows_file(rows, "csv"))
    file_id = response.json()["id"]
    await jobs.drain()
    mapping: dict[str, Any] = {"inputs": {"ticket": "ticket"}}
    if "expected" in rows[0]:
        mapping["expected_output"] = "expected"
    assert (await map_file(client, session, file_id, version_id, mapping)).status_code == 200
    await jobs.drain()
    assert (await import_file(client, session, file_id)).status_code == 200
    await jobs.drain()


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
    await ingest(client, session, jobs, prompt["id"], GOLDEN)
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
    await ingest(client, session, jobs, prompt["id"], GOLDEN)
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
