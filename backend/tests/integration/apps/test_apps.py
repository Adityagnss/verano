"""
Testing the user's own app over HTTP (ADR 0024 to 0026): an app is connected, one test case is sent and shown exactly,
an experiment runs the app next to models on the same cases, the answer, retrieved chunks and tool calls are stored and
scored, a failing app is a failed answer and never a pass, secrets never come back, and internal addresses are refused.
"""

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import httpx
import pytest

from app.core.jobs import InlineJobQueue
from tests.helpers import Session, approved_project, base, judged_project

pytestmark = [pytest.mark.integration]

LABELS = {"charged": "billing", "parcel": "shipping", "crashes": "technical"}


class FakeApp(BaseHTTPRequestHandler):
    """A tiny support app: it classifies a ticket, reports what it retrieved and the tool it called."""

    seen: list[dict[str, Any]] = []

    def do_POST(self) -> None:
        sent = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeApp.seen.append({"body": sent, "auth": self.headers.get("Authorization")})
        message = str(sent.get("message", ""))
        if "parcel" in message:
            self._reply(500, {"error": "the shipping service is down"})
            return
        label = next((v for k, v in LABELS.items() if k in message), "other")
        self._reply(
            200,
            {
                "answer": label,
                "sources": [{"id": "kb-1", "text": f"policy for {label}"}],
                "tool_calls": [{"name": "lookup", "arguments": {"topic": label}}],
            },
        )

    def _reply(self, status: int, body: dict[str, Any]) -> None:
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *args: Any) -> None:
        return


@pytest.fixture
def fake_app() -> Iterator[str]:
    FakeApp.seen = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeApp)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}/ask"
    server.shutdown()
    server.server_close()


def app_body(url: str, **extra: Any) -> dict[str, Any]:
    return {
        "name": "Support app",
        "url": url,
        "request_template": '{"message": {{ attachment | tojson }}}',
        "answer_path": "$.answer",
        "chunks_path": "$.sources[*].text",
        "tool_calls_path": "$.tool_calls",
        **extra,
    }


async def connect(client: httpx.AsyncClient, session: Session, url: str, **extra: Any) -> dict[str, Any]:
    response = await client.post(f"{base(session)}/apps", json=app_body(url, **extra), headers=session.headers)
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


async def test_one_test_case_shows_what_was_sent_what_came_back_and_what_was_read(
    client: httpx.AsyncClient, session: Session, fake_app: str
) -> None:
    app = await connect(client, session, fake_app, auth_kind="bearer", bearer_token="s3cret-token")
    assert "s3cret-token" not in json.dumps(app)
    assert app["auth_kind"] == "bearer"
    assert app["header_names"] == ["Authorization"]  # names only; the value is never returned
    shown = await client.post(
        f"{base(session)}/apps/{app['id']}/test",
        json={"inputs": {"attachment": "I was charged twice"}},
        headers=session.headers,
    )
    body = shown.json()
    assert json.loads(body["request_body"]) == {"message": "I was charged twice"}
    assert body["status_code"] == 200
    assert body["error"] is None
    assert body["reply"] == {
        "answer": "billing",
        "chunks": ["policy for billing"],
        "tool_calls": [{"name": "lookup", "arguments": {"topic": "billing"}}],
        "cost": None,
    }
    assert FakeApp.seen[0]["auth"] == "Bearer s3cret-token"  # the app received the secret


async def test_a_wrong_mapping_says_where_it_looked_and_shows_the_reply(
    client: httpx.AsyncClient, session: Session, fake_app: str
) -> None:
    app = await connect(client, session, fake_app, answer_path="$.data.answer")
    shown = (
        await client.post(
            f"{base(session)}/apps/{app['id']}/test",
            json={"inputs": {"attachment": "charged"}},
            headers=session.headers,
        )
    ).json()
    assert shown["reply"] is None
    assert "Nothing found at $.data.answer" in shown["error"]
    assert "billing" in shown["response_body"]


@pytest.mark.parametrize(
    "url", ["http://localhost:9/x", "http://169.254.169.254/latest/meta-data", "http://10.0.0.5/x"]
)
async def test_internal_addresses_are_refused_unless_the_host_is_allowed(
    client: httpx.AsyncClient, session: Session, url: str
) -> None:
    app = await connect(client, session, url)
    shown = (
        await client.post(
            f"{base(session)}/apps/{app['id']}/test", json={"inputs": {"attachment": "x"}}, headers=session.headers
        )
    ).json()
    assert shown["reply"] is None
    assert shown["error"]
    assert shown["status_code"] is None  # nothing was sent


async def test_an_app_runs_next_to_models_and_its_answers_chunks_and_tool_calls_are_scored(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, fake_app: str
) -> None:
    models = await approved_project(client, session, jobs)
    app = await connect(client, session, fake_app)
    selected = {
        m["model_name"]: m["id"]
        for m in (await client.get(f"{base(session)}/models", params={"limit": 200}, headers=session.headers)).json()[
            "items"
        ]
    }
    assert app["model_profile_id"] in selected.values()  # the app is one more column next to the models
    body = {
        "models": [
            {"model_profile_id": app["model_profile_id"], "runs": 1},
            {"model_profile_id": models["good"], "runs": 1},
        ]
    }
    started = await client.post(f"{base(session)}/experiments", json=body, headers=session.headers)
    assert started.status_code == 201, started.text
    await jobs.drain()

    cases = (
        await client.get(f"{base(session)}/experiments/{started.json()['id']}/cases", headers=session.headers)
    ).json()
    outputs = [o for case in cases for o in case["outputs"] if o["model"] == "Support app"]
    assert len(outputs) == 3
    ok = [o for o in outputs if o["error"] is None]
    failed = [o for o in outputs if o["error"] is not None]
    assert len(ok) == 2
    assert len(failed) == 1
    assert "status 500" in failed[0]["error"]
    assert failed[0]["passed"] is False
    assert ok[0]["retrieved_chunks"] == [f"policy for {ok[0]['output']}"]
    assert ok[0]["tool_calls"] == [{"name": "lookup", "arguments": {"topic": ok[0]["output"]}}]
    assert all(o["judged"] and o["passed"] for o in ok)  # the labels match the golden answers

    # the exchange with the app is kept per case and can be read back
    experiment_id = started.json()["id"]
    sent = (
        await client.get(
            f"{base(session)}/apps/calls/{experiment_id}/{ok[0]['test_case_run_id']}", headers=session.headers
        )
    ).json()
    assert len(sent) == 1
    assert sent[0]["status_code"] == 200
    assert sent[0]["request_body"]
    assert sent[0]["response_body"]
    nothing = await client.get(
        f"{base(session)}/apps/calls/{experiment_id}/{failed[0]['test_case_run_id']}", headers=session.headers
    )
    assert nothing.status_code == 200

    # scoring again re-reads the stored answers: it makes no call to the app (replay)
    calls_before = len(FakeApp.seen)
    again = await client.post(
        f"{base(session)}/experiments/{started.json()['id']}/rescore", json={}, headers=session.headers
    )
    assert again.status_code == 202, again.text
    await jobs.drain()
    assert len(FakeApp.seen) == calls_before


async def test_an_app_can_be_changed_and_removed_and_stays_out_of_the_keys_list(
    client: httpx.AsyncClient, session: Session, fake_app: str
) -> None:
    app = await connect(client, session, fake_app)
    keys = (await client.get(f"{base(session)}/credentials", headers=session.headers)).json()
    assert all(k["provider"] != "app" for k in (keys["items"] if isinstance(keys, dict) else keys))
    changed = await client.patch(
        f"{base(session)}/apps/{app['id']}", json={"timeout_s": 5, "retries": 1}, headers=session.headers
    )
    assert (changed.json()["timeout_s"], changed.json()["retries"]) == (5.0, 1)
    assert (await client.delete(f"{base(session)}/apps/{app['id']}", headers=session.headers)).status_code == 204
    assert (await client.get(f"{base(session)}/apps", headers=session.headers)).json() == []


async def test_a_bearer_app_without_a_token_is_refused_with_what_is_missing(
    client: httpx.AsyncClient, session: Session, fake_app: str
) -> None:
    refused = await client.post(
        f"{base(session)}/apps", json=app_body(fake_app, auth_kind="bearer"), headers=session.headers
    )
    assert refused.status_code == 422
    assert "token" in refused.text


async def test_a_conversation_with_an_app_is_run_by_a_simulated_user_and_stored_as_a_transcript(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue, fake_app: str
) -> None:
    models = await judged_project(client, session, jobs, set_judge="echo")
    app = await connect(
        client, session, fake_app, mode="conversation", request_template='{"message": {{ message | tojson }}}'
    )
    body = {"models": [{"model_profile_id": app["model_profile_id"], "runs": 1}]}
    started = await client.post(f"{base(session)}/experiments", json=body, headers=session.headers)
    assert started.status_code == 201, started.text
    await jobs.drain()

    cases = (
        await client.get(f"{base(session)}/experiments/{started.json()['id']}/cases", headers=session.headers)
    ).json()
    outputs = [o for case in cases for o in case["outputs"]]
    assert len(outputs) == 3
    assert all(o["error"] is None for o in outputs), [o["error"] for o in outputs]
    transcript = json.loads(outputs[0]["output"])
    assert transcript["ended"] in {"turn_limit", "goal_reached"}
    roles = [turn["role"] for turn in transcript["turns"]]
    assert roles[:2] == ["user", "assistant"]
    assert roles.count("assistant") >= 1
    assert models["_credential"]  # the simulated user was the experiment's judge model (the mock "echo")
