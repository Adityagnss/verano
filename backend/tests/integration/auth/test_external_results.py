"""Integration tests for results computed elsewhere (pytest reports) and sent to Verano with a token."""

import uuid

import httpx
import pytest

from tests.helpers import Session, base

pytestmark = [pytest.mark.integration]

REPORT = {
    "source": "pytest",
    "name": "tests/test_bot.py",
    "cases": [
        {"name": "refund", "passed": True, "answer": "5 days"},
        {"name": "shipping", "passed": False, "problems": ["expected 'x'"], "answer": "y" * 5000},
    ],
    "details": {"commit": "abc123"},
}


async def token(client: httpx.AsyncClient, session: Session, **body: object) -> dict[str, str]:
    response = await client.post("/api/v1/auth/tokens", json={"name": "ci", **body}, headers=session.headers)
    return {"Authorization": f"Bearer {response.json()['token']}"}


async def test_results_sent_with_a_token_are_counted_stored_cut_and_listed(
    client: httpx.AsyncClient, session: Session
) -> None:
    headers = await token(client, session, project_id=str(session.project_id))
    url = f"{base(session)}/external-results"
    sent = await client.post(url, json=REPORT, headers=headers)
    assert sent.status_code == 201, sent.text
    body = sent.json()
    assert (body["passed"], body["failed"], body["details"]) == (1, 1, {"commit": "abc123"})
    assert len(body["cases"][1]["answer"]) == 2000

    listed = (await client.get(url, headers=session.headers)).json()["items"]
    assert [(r["id"], r["passed"], r["failed"]) for r in listed] == [(body["id"], 1, 1)]
    assert "cases" not in listed[0]
    full = await client.get(f"{url}/{body['id']}", headers=session.headers)
    assert [c["name"] for c in full.json()["cases"]] == ["refund", "shipping"]
    assert (await client.get(f"{url}/{uuid.uuid4()}", headers=session.headers)).status_code == 404


async def test_a_read_only_token_a_foreign_project_and_bad_bodies_are_refused(
    client: httpx.AsyncClient, session: Session
) -> None:
    url = f"{base(session)}/external-results"
    read = await token(client, session, scope="read")
    refused = await client.post(url, json=REPORT, headers=read)
    assert refused.status_code == 403
    assert (await client.get(url, headers=read)).status_code == 200

    other = (await client.post("/api/v1/projects", json={"name": "Other"}, headers=session.headers)).json()
    bound = await token(client, session, project_id=other["id"])
    assert (await client.post(url, json=REPORT, headers=bound)).status_code == 404

    for bad in ({**REPORT, "source": "Bad Source"}, {**REPORT, "name": ""}, {"name": "x"}):
        assert (await client.post(url, json=bad, headers=session.headers)).status_code == 422
    assert (await client.post(url, json=REPORT)).status_code == 401
    assert (await client.get(url, headers=session.headers)).json()["items"] == []
