"""
Integration tests for the Eval Generator and Review & Approve on mock/scripted: Task Spec
draft and confirmation, gap-filling generation grounded in a document, dedupe, label
balance, drafted answers that never touch golden rows, evaluator selection, mandatory
review, the stratified 70/30 split, the frozen version, and "Use only my golden set".
Also the safety limits: cancel, the generation budget cap and the cost confirmation.
"""

import uuid
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


async def test_a_task_spec_you_wrote_is_confirmed_without_any_model_call_and_repeating_it_is_harmless(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, container: Container
) -> None:
    prompt = await create_prompt(client, session)
    await ingest(client, session, jobs, GOLDEN)
    path = api(session, f"/prompt-versions/{prompt['id']}/task-spec")
    written = {
        "task_type": "classification",
        "goal": "Label each support ticket",
        "output_format": "single_label",
        "allowed_outputs": ["billing", "shipping", "technical"],
    }
    first = await client.put(path, json={"spec": written}, headers=session.headers)
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "confirmed"
    assert first.json()["spec"]["input_variables"] == ["ticket"]
    assert first.json()["generator_model"] is None
    again = await client.put(path, json={"spec": written}, headers=session.headers)
    assert again.json()["id"] == first.json()["id"]
    changed = await client.put(
        path, json={"spec": {**written, "goal": "Label tickets by team"}}, headers=session.headers
    )
    assert changed.json()["id"] != first.json()["id"]

    async with container.database.sessions() as db:
        calls = (await db.scalars(select(LLMCall).where(LLMCall.purpose == "generation"))).all()
    assert list(calls) == []
    for route in ("/generations/estimate", "/generations"):  # nothing to write cases with: said up front
        refused = await client.post(
            api(session, route), json={"task_spec_id": first.json()["id"]}, headers=session.headers
        )
        assert refused.status_code == 409, refused.text
        assert "no model to write test cases with" in refused.json()["error"]["message"]
    started = await client.post(
        api(session, "/generations"),
        json={"task_spec_id": first.json()["id"], "golden_only": True},
        headers=session.headers,
    )
    assert started.status_code == 202, started.text
    await jobs.drain()


async def test_a_written_task_spec_is_checked_and_its_judge_must_be_one_of_your_models(
    client: httpx.AsyncClient, session: Session
) -> None:
    prompt = await create_prompt(client, session)
    path = api(session, f"/prompt-versions/{prompt['id']}/task-spec")
    base = {"task_type": "summarization", "goal": "Summarize the ticket", "output_format": "free_text"}
    for bad in (
        {**base, "task_type": "classification"},
        {**base, "goal": "x"},
        {**base, "input_variables": ["other"]},
        {**base, "task_type": "poetry"},
    ):
        response = await client.put(path, json={"spec": bad}, headers=session.headers)
        assert response.status_code == 422, bad
    credential = await add_credential(client, session, "mock")
    unknown = await client.put(
        path,
        json={"spec": base, "judge": {"credential_id": credential["id"], "model": "no-such-model"}},
        headers=session.headers,
    )
    assert unknown.status_code == 404
    judged = await client.put(
        path,
        json={"spec": base, "judge": {"credential_id": credential["id"], "model": "scripted"}},
        headers=session.headers,
    )
    assert judged.status_code == 200, judged.text
    assert judged.json()["generator_model"] == "scripted"
    missing = await client.put(
        api(session, f"/prompt-versions/{uuid.uuid4()}/task-spec"), json={"spec": base}, headers=session.headers
    )
    assert missing.status_code == 404


async def test_a_prompt_with_no_variables_is_not_given_generated_cases(
    client: httpx.AsyncClient, session: Session
) -> None:
    prompt = await create_prompt(
        client, session, system_template="Draft the rule.", user_template="All the data, pasted."
    )
    credential = await add_credential(client, session, "mock")
    body = {"prompt_version_id": prompt["id"], "credential_id": credential["id"], "model": "scripted"}
    drafted = (await client.post(api(session, "/task-specs"), json=body, headers=session.headers)).json()
    assert drafted["spec"]["input_variables"] == []
    await client.put(
        api(session, f"/task-specs/{drafted['id']}"), json={"spec": drafted["spec"]}, headers=session.headers
    )
    refused = await client.post(
        api(session, "/generations/estimate"), json={"task_spec_id": drafted["id"]}, headers=session.headers
    )
    assert refused.status_code == 409, refused.text
    assert "no {{ variables }}" in refused.json()["error"]["message"]
