"""S8.7: test cases made from traffic are drafts, deduplicated, never made twice, and unused until approved."""

import uuid
from typing import Any

import httpx
import pytest

from app.core.container import Container
from tests import traffic_samples as samples
from tests.helpers import Session, base
from tests.traffic_support import import_data, tbase, trace_rows, traces

pytestmark = [pytest.mark.integration]

TOPICS = [
    "How do I reset my password",
    "Where is my parcel for order {n}",
    "Why was my card charged twice",
    "Cancel my subscription now",
    "The mobile app crashes when I open settings",
]


WORDS = [
    "alpine",
    "bronze",
    "cobalt",
    "dahlia",
    "ember",
    "fjord",
    "garnet",
    "harbor",
    "indigo",
    "jasper",
    "kestrel",
    "lagoon",
    "meadow",
    "nectar",
    "orchid",
    "pebble",
    "quartz",
    "ripple",
    "saffron",
    "thistle",
    "umber",
    "velvet",
    "willow",
    "xenon",
    "yarrow",
    "zephyr",
    "almond",
    "basalt",
    "cedar",
    "dune",
    "elm",
    "falcon",
    "glacier",
    "heron",
    "ivory",
    "juniper",
    "kelp",
    "lichen",
    "marble",
    "nutmeg",
    "onyx",
    "pine",
    "quill",
    "raven",
    "sable",
    "tundra",
    "urchin",
    "violet",
    "walnut",
    "yucca",
    "zinc",
]


def distinct_questions(count: int) -> list[str]:
    """Questions that share no words with each other, so none counts as a near-duplicate."""
    return [" ".join(WORDS[(i * 4 + k) % len(WORDS)] for k in range(4)) + "?" for i in range(count)]


async def import_questions(client: httpx.AsyncClient, session: Session, questions: list[str], start: int = 0) -> None:
    spans = [samples.otel_span(start + i, q, f"answer {i}") for i, q in enumerate(questions, start=1)]
    assert (await import_data(client, session, samples.otel_export(spans))).status_code == 201


async def make(client: httpx.AsyncClient, session: Session, **body: Any) -> dict[str, Any]:
    response = await client.post(f"{tbase(session)}/cases", json=body, headers=session.headers)
    assert response.status_code == 200, response.text
    out: dict[str, Any] = response.json()
    return out


async def draft_items(client: httpx.AsyncClient, session: Session, version_id: str) -> list[dict[str, Any]]:
    response = await client.get(
        f"{base(session)}/dataset-versions/{version_id}/items", params={"limit": 200}, headers=session.headers
    )
    assert response.status_code == 200, response.text
    items: list[dict[str, Any]] = response.json()["items"]
    return items


async def test_a_hundred_traces_become_deduplicated_draft_cases_that_are_not_used_until_approved(
    client: httpx.AsyncClient, session: Session
) -> None:
    unique = distinct_questions(25)
    await import_questions(client, session, [q for q in unique for _ in range(4)])  # 100 traces, 25 questions
    assert len(await traces(client, session)) == 100

    out = await make(client, session, filter={"unused": True}, max_cases=100)
    assert out["considered"] == 100
    assert out["created"] == 25
    assert out["folded"] == 75
    assert out["dry_run"] is False
    assert "not used until you review" in out["message"]

    items = await draft_items(client, session, out["dataset_version_id"])
    assert len(items) == 25
    assert {i["review_status"] for i in items} == {"draft"}
    assert {i["source"] for i in items} == {"traffic"}
    assert {i["category"] for i in items} == {"from_traffic"}
    assert {tuple(i["inputs"]) for i in items} == {("input",)}
    assert sorted(i["inputs"]["input"] for i in items) == sorted(unique)
    assert all(i["extra"]["similar_traces_folded"] == 3 for i in items)

    approve = await client.post(
        f"{base(session)}/dataset-versions/{out['dataset_version_id']}/approve", headers=session.headers
    )
    assert approve.status_code == 422
    assert "review" in approve.json()["error"]["message"].lower()
    version = (
        await client.get(f"{base(session)}/dataset-versions/{out['dataset_version_id']}", headers=session.headers)
    ).json()
    assert version["status"] == "draft"


async def test_a_dry_run_reports_what_would_happen_and_changes_nothing(
    client: httpx.AsyncClient, session: Session, container: Container
) -> None:
    await import_questions(client, session, distinct_questions(6))
    out = await make(client, session, filter={"unused": True}, dry_run=True)
    assert out["dry_run"]
    assert out["created"] == 6
    assert out["dataset_version_id"] is None
    assert "Nothing was changed" in out["message"]
    assert all(r.case_made_at is None for r in await trace_rows(container, session))
    assert (await client.get(f"{base(session)}/dataset-versions/current", headers=session.headers)).status_code == 404
    assert (await make(client, session, filter={"unused": True}))["created"] == 6  # a real run still finds them all


async def test_traces_already_made_into_cases_are_never_made_twice(client: httpx.AsyncClient, session: Session) -> None:
    await import_questions(client, session, distinct_questions(5))
    first = await make(client, session, filter={})
    assert first["created"] == 5
    again = await make(client, session, filter={})  # the filter only selects unused traces
    assert again["created"] == 0
    assert again["considered"] == 0
    assert "No new cases" in again["message"]
    ids = [t["id"] for t in await traces(client, session)]
    by_id = await make(client, session, trace_ids=ids)
    assert by_id["created"] == 0
    assert by_id["already_used"] == 5
    assert all(t["case_made"] for t in await traces(client, session))
    assert len(await draft_items(client, session, first["dataset_version_id"])) == 5


async def test_new_traces_are_folded_into_cases_already_in_the_draft(
    client: httpx.AsyncClient, session: Session
) -> None:
    old = distinct_questions(5)
    await import_questions(client, session, old)
    first = await make(client, session, filter={})
    await import_questions(client, session, [old[0], old[1], "A completely different question about invoices"], 50)
    second = await make(client, session, filter={"unused": True})
    assert second["considered"] == 3
    assert second["created"] == 1
    assert second["folded"] == 2
    assert second["dataset_version_id"] == first["dataset_version_id"]
    assert len(await draft_items(client, session, first["dataset_version_id"])) == 6


async def test_the_filter_picks_only_failed_or_low_rated_traces(client: httpx.AsyncClient, session: Session) -> None:
    await import_data(client, session, samples.langfuse_sample())
    failed = await make(client, session, filter={"failed": True}, dry_run=True)
    assert failed["considered"] == 1
    low = await make(client, session, filter={"low_rated": True})
    assert low["created"] == 1
    items = await draft_items(client, session, low["dataset_version_id"])
    assert items[0]["inputs"]["input"] == "My card was declined"
    assert items[0]["extra"]["observed_output"] == "Try another card."
    assert items[0]["tags"] == ["from_traffic", "langfuse"]


async def test_the_input_variable_name_and_the_cap_on_cases_are_respected(
    client: httpx.AsyncClient, session: Session
) -> None:
    await import_questions(client, session, distinct_questions(8))
    out = await make(client, session, filter={}, variable="ticket", max_cases=3)
    assert out["considered"] == 3
    assert out["created"] == 3
    assert {tuple(i["inputs"]) for i in await draft_items(client, session, out["dataset_version_id"])} == {("ticket",)}


async def test_a_trace_with_no_question_is_counted_as_empty_and_makes_no_case(
    client: httpx.AsyncClient, session: Session
) -> None:
    span = samples.otel_span(1, "", "only an answer")
    span["attributes"] = [a for a in span["attributes"] if a["key"] != "gen_ai.input.messages"]
    await import_data(client, session, samples.otel_export([span]))
    out = await make(client, session, filter={})
    assert out["empty"] == 1
    assert out["created"] == 0


async def test_unknown_trace_ids_and_an_empty_request_are_refused(client: httpx.AsyncClient, session: Session) -> None:
    missing = await client.post(
        f"{tbase(session)}/cases", json={"trace_ids": [str(uuid.uuid4())]}, headers=session.headers
    )
    assert missing.status_code == 404
    neither = await client.post(f"{tbase(session)}/cases", json={}, headers=session.headers)
    assert neither.status_code == 422


async def test_traffic_cases_are_labelled_apart_from_uploaded_ones_in_the_summary(
    client: httpx.AsyncClient, session: Session
) -> None:
    await import_questions(client, session, distinct_questions(4))
    out = await make(client, session, filter={})
    summary = (
        await client.get(f"{base(session)}/dataset-versions/{out['dataset_version_id']}", headers=session.headers)
    ).json()
    sources = {row.get("source", k): row for k, row in summary["by_source"].items()}
    assert set(summary["by_source"]) == {"traffic"}
    assert sources["traffic"]["draft"] == 4
    assert sources["traffic"]["without_answer"] == 0  # a real question with no golden answer is not a problem


async def test_traffic_cases_can_be_approved_like_any_draft_using_the_checks_the_project_already_has(
    client: httpx.AsyncClient, session: Session, jobs: Any
) -> None:
    from tests.helpers import approved_project

    await approved_project(client, session, jobs)  # an approved version with golden cases
    await import_questions(client, session, distinct_questions(5))
    out = await make(client, session, filter={})
    assert out["created"] == 5
    draft_id = out["dataset_version_id"]
    drafts = f"{base(session)}/dataset-versions/{draft_id}"
    early = await client.post(f"{drafts}/approve", headers=session.headers)
    assert early.status_code == 422  # the five traffic drafts are not reviewed yet
    reviewed = await client.post(f"{drafts}/approve-drafts", json={"source": "traffic"}, headers=session.headers)
    assert reviewed.status_code == 200, reviewed.text
    approved = await client.post(f"{drafts}/approve", headers=session.headers)
    assert approved.status_code == 200, approved.text
    items = await draft_items(client, session, draft_id)
    assert {i["source"] for i in items} == {"traffic"}
    assert len(items) == 5
    assert {i["review_status"] for i in items} <= {"approved", "trusted"}
