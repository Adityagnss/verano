"""The Python SDK against a small fake Verano: a fetch, the cache and its ETag, the fallback when Verano cannot be
reached, a refusal that the cache must never hide, and rendering (scenario S8.2)."""

import json
import threading
import warnings
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from verano_sdk import Verano, VeranoError, VeranoRefused, VeranoUnreachable

PROJECT = "11111111-2222-3333-4444-555555555555"
PROMPT = {
    "name": "triage",
    "label": "production",
    "version": 3,
    "version_id": "v3",
    "system_template": "You triage tickets for {{ team }}.",
    "user_template": "Ticket: {{ ticket }}",
    "variables": ["team", "ticket"],
    "default_params": {"temperature": 0},
    "updated_at": "2026-11-10T09:00:00Z",
}


class FakeVerano:
    """Answers `prompt-by-name` with the current prompt and an ETag; what it does next is set by the test."""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.prompt: dict[str, Any] = dict(PROMPT)
        self.status = 200
        self.etag = '"v3"'
        handler = self._handler()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}"

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                outer.requests.append({"path": self.path, "headers": dict(self.headers.items())})
                if outer.status != 200:
                    body = json.dumps({"error": {"message": f"fake answer {outer.status}"}}).encode()
                    self.send_response(outer.status)
                elif self.headers.get("If-None-Match") == outer.etag:
                    body = b""
                    self.send_response(304)
                else:
                    body = json.dumps(outer.prompt).encode()
                    self.send_response(200)
                    self.send_header("ETag", outer.etag)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: Any) -> None:
                return

        return Handler

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def fake() -> Iterator[FakeVerano]:
    server = FakeVerano()
    yield server
    server.stop()


def client(fake: FakeVerano, tmp_path: Path, **extra: Any) -> Verano:
    return Verano(base_url=fake.url, token="vrn_test", project_id=PROJECT, cache_dir=tmp_path / "cache", **extra)


def test_a_prompt_is_fetched_for_its_label_with_the_token_and_saved(fake: FakeVerano, tmp_path: Path) -> None:
    prompt = client(fake, tmp_path).prompt("triage", label="staging")
    assert (prompt.name, prompt.version, prompt.from_cache) == ("triage", 3, False)
    request = fake.requests[0]
    assert request["path"] == f"/api/v1/projects/{PROJECT}/prompt-by-name/triage?label=staging"
    assert request["headers"]["Authorization"] == "Bearer vrn_test"
    assert list((tmp_path / "cache").glob("*.json"))


def test_an_unchanged_prompt_costs_an_empty_answer_because_the_saved_etag_is_sent(
    fake: FakeVerano, tmp_path: Path
) -> None:
    verano = client(fake, tmp_path)
    verano.prompt("triage")
    again = verano.prompt("triage")
    assert fake.requests[1]["headers"]["If-None-Match"] == '"v3"'
    assert again.version == 3
    assert again.from_cache is False


def test_a_changed_prompt_replaces_the_saved_copy(fake: FakeVerano, tmp_path: Path) -> None:
    verano = client(fake, tmp_path)
    verano.prompt("triage")
    fake.prompt = {**PROMPT, "version": 4, "version_id": "v4", "system_template": "New text."}
    fake.etag = '"v4"'
    assert verano.prompt("triage").version == 4
    fake.stop()  # the next call falls back to the newest saved copy, not the first one
    with pytest.warns(UserWarning, match="saved copy"):
        assert verano.prompt("triage").system_template == "New text."


def test_when_verano_cannot_be_reached_the_saved_copy_is_served_with_a_warning(
    fake: FakeVerano, tmp_path: Path
) -> None:
    verano = client(fake, tmp_path)
    verano.prompt("triage")
    fake.stop()
    with pytest.warns(UserWarning, match="could not be reached"):
        prompt = verano.prompt("triage")
    assert prompt.from_cache is True
    assert prompt.version == 3


def test_a_server_error_also_falls_back_to_the_saved_copy(fake: FakeVerano, tmp_path: Path) -> None:
    verano = client(fake, tmp_path)
    verano.prompt("triage")
    fake.status = 503
    with pytest.warns(UserWarning, match="saved copy"):
        assert verano.prompt("triage").from_cache is True


def test_with_nothing_saved_an_outage_is_an_error_that_says_so(fake: FakeVerano, tmp_path: Path) -> None:
    fake.stop()
    with pytest.raises(VeranoUnreachable):
        client(fake, tmp_path).prompt("triage")


@pytest.mark.parametrize("status", [401, 403, 404])
def test_a_no_from_verano_is_raised_and_never_hidden_behind_the_cache(
    fake: FakeVerano, tmp_path: Path, status: int
) -> None:
    verano = client(fake, tmp_path)
    verano.prompt("triage")  # a good copy is saved
    fake.status = status
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # no fallback warning either
        with pytest.raises(VeranoRefused) as refused:
            verano.prompt("triage")
    assert refused.value.args[0] == f"fake answer {status}"


def test_the_address_the_token_and_the_project_are_all_needed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("VERANO_URL", "VERANO_API_TOKEN", "VERANO_PROJECT_ID"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(VeranoError, match="read-only token"):
        Verano(base_url="http://localhost:8080", cache_dir=tmp_path)
    monkeypatch.setenv("VERANO_URL", "http://localhost:8080")
    monkeypatch.setenv("VERANO_API_TOKEN", "vrn_x")
    monkeypatch.setenv("VERANO_PROJECT_ID", PROJECT)
    Verano(cache_dir=tmp_path)  # all three from the environment


def test_a_pinned_version_ignores_the_label_and_max_age_skips_the_request(fake: FakeVerano, tmp_path: Path) -> None:
    verano = client(fake, tmp_path, max_age=60)
    verano.prompt("triage", version=2)
    assert fake.requests[0]["path"].endswith("?version=2")
    verano.prompt("triage", version=2)
    assert len(fake.requests) == 1  # served from memory inside max_age


def test_a_cache_that_cannot_be_written_never_breaks_the_app(fake: FakeVerano, tmp_path: Path) -> None:
    blocked = tmp_path / "file"
    blocked.write_text("not a folder")
    prompt = Verano(base_url=fake.url, token="t", project_id=PROJECT, cache_dir=blocked / "cache").prompt("triage")
    assert prompt.version == 3


def test_a_corrupt_saved_copy_is_ignored_and_replaced(fake: FakeVerano, tmp_path: Path) -> None:
    verano = client(fake, tmp_path)
    verano.prompt("triage")
    for path in (tmp_path / "cache").glob("*.json"):
        path.write_text("{ not json")
    assert verano.prompt("triage").version == 3
    assert "If-None-Match" not in fake.requests[1]["headers"]


def test_render_fills_every_placeholder_and_names_what_is_missing(fake: FakeVerano, tmp_path: Path) -> None:
    prompt = client(fake, tmp_path).prompt("triage")
    system, user = prompt.render(team="billing", ticket="I was charged twice")
    assert system == "You triage tickets for billing."
    assert user == "Ticket: I was charged twice"
    with pytest.raises(VeranoError, match="ticket"):
        prompt.render(team="billing")
