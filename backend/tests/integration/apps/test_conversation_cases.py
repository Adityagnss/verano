"""
Writing conversation cases for an app that talks (ADR 0039): the model's cases are saved as drafts of the project's
draft dataset, repeats and blank cases are dropped, turns never exceed the server's cap, and a one-message app is
refused. The scripted mock model answers the request from fixtures/scripted/responses/conversation_cases.yaml.
"""

from typing import Any

import httpx
import pytest

from app.core.jobs import InlineJobQueue
from tests.helpers import Session, base, judged_project

pytestmark = [pytest.mark.integration]

APP = {
    "name": "Talking app",
    "url": "http://127.0.0.1:9/chat",
    "mode": "conversation",
    "request_template": '{"message": {{ message | tojson }}}',
    "answer_path": "$.answer",
}


async def connect(client: httpx.AsyncClient, session: Session, **extra: Any) -> dict[str, Any]:
    response = await client.post(f"{base(session)}/apps", json={**APP, **extra}, headers=session.headers)
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


async def items(client: httpx.AsyncClient, session: Session, version_id: str) -> list[dict[str, Any]]:
    page = (
        await client.get(
            f"{base(session)}/dataset-versions/{version_id}/items",
            params={"source": "generated", "limit": 100},
            headers=session.headers,
        )
    ).json()
    found: list[dict[str, Any]] = page["items"]
    return found


async def test_cases_are_written_as_drafts_with_repeats_blanks_and_long_conversations_handled(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue
) -> None:
    models = await judged_project(client, session, jobs, set_judge="scripted")
    app = await connect(client, session)
    generator = {"credential_id": models["_credential"], "model": "scripted"}
    done = await client.post(
        f"{base(session)}/apps/{app['id']}/conversation-cases",
        json={"count": 3, "generator": generator},
        headers=session.headers,
    )
    assert done.status_code == 201, done.text
    out = done.json()
    assert out["added"] == 3 - 1  # the model wrote four; one repeats a goal and one has a blank persona
    assert out["dropped_duplicates"] >= 1
    assert out["dropped_invalid"] >= 1
    assert "left out because they repeat" in out["message"]
    assert out["generator_model"] == "scripted"

    rows = await items(client, session, out["dataset_version_id"])
    drafts = [r for r in rows if r["inputs"].get("goal")]
    assert len(drafts) == 2
    assert all(r["review_status"] == "draft" for r in drafts)
    first = next(r for r in drafts if r["inputs"]["goal"] == "Get a refund for a double charge")
    assert first["rubric"] == [first["inputs"]["stop_when"]]  # the judges read the stopping condition
    assert first["inputs"]["max_turns"] == 4
    long = next(r for r in drafts if r["inputs"]["goal"] == "Change the delivery address")
    assert long["inputs"]["max_turns"] == 8  # asked for 99; the server allows 8
    assert long["inputs"]["scenario"] == "Order shipped yesterday"

    again = await client.post(
        f"{base(session)}/apps/{app['id']}/conversation-cases",
        json={"count": 3, "generator": generator},
        headers=session.headers,
    )
    assert again.json()["added"] == 0  # everything it writes is already there
    assert again.json()["dropped_duplicates"] >= 2
    assert len(await items(client, session, out["dataset_version_id"])) == len(rows)


async def test_a_one_message_app_a_missing_app_and_a_missing_prompt_are_refused(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue
) -> None:
    plain = await connect(client, session, mode="single", request_template='{"message": {{ attachment | tojson }}}')
    no_prompt = await client.post(
        f"{base(session)}/apps/{plain['id']}/conversation-cases", json={}, headers=session.headers
    )
    assert no_prompt.status_code == 422
    assert "conversation mode" in no_prompt.text
    gone = await client.post(
        f"{base(session)}/apps/00000000-0000-0000-0000-000000000000/conversation-cases",
        json={},
        headers=session.headers,
    )
    assert gone.status_code == 404
    talking = await connect(client, session, name="Chat")
    empty = await client.post(
        f"{base(session)}/apps/{talking['id']}/conversation-cases", json={}, headers=session.headers
    )
    assert empty.status_code == 422
    assert "Save a prompt" in empty.text
