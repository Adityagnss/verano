"""A fake Verano server and a way to run the real `verano` command against it."""

import io
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
import pytest

from verano import client
from verano.cli import main

if TYPE_CHECKING:
    from tests.platform import FakePlatform

SESSION = "session-jwt"


@dataclass
class FakeVerano:
    """Just enough of the API for sign-in and tokens; every request is recorded."""

    password: str = "correct horse battery"
    down: bool = False
    html: bool = False
    fail_with: dict[tuple[str, str], httpx.Response] = field(default_factory=dict)
    calls: list[tuple[str, str]] = field(default_factory=list)
    bodies: list[Any] = field(default_factory=list)
    tokens: dict[str, dict[str, Any]] = field(default_factory=dict)
    issued: int = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("refused", request=request)
        path = request.url.path.removeprefix("/api/v1")
        key = (request.method, path)
        self.calls.append(key)
        is_json = request.headers.get("content-type", "").startswith("application/json")
        self.bodies.append(json.loads(request.content) if request.content and is_json else None)
        if self.html:
            return httpx.Response(200, text="<html>Welcome</html>")
        if key in self.fail_with:
            return self.fail_with[key]
        return self.route(request, path)

    def route(self, request: httpx.Request, path: str) -> httpx.Response:
        bearer = request.headers.get("authorization", "").removeprefix("Bearer ")
        is_json = request.headers.get("content-type", "").startswith("application/json")
        body = json.loads(request.content) if request.content and is_json else {}
        if (request.method, path) == ("POST", "/auth/login"):
            if body.get("password") != self.password:
                return error(401, "That email and password don't match an account. Check them and try again.")
            return httpx.Response(200, json={"access_token": SESSION, "user": {"email": body["email"], "name": "Ada"}})
        if (request.method, path) == ("DELETE", "/auth/refresh"):
            return httpx.Response(204)
        if bearer != SESSION and bearer not in {t["token"] for t in self.tokens.values()}:
            return error(401, "This API token is invalid, expired or revoked.")
        if (request.method, path) == ("POST", "/auth/tokens"):
            if bearer != SESSION:
                return error(403, "Create API tokens while signed in, not with another API token.")
            self.issued += 1
            made = {
                "id": f"tok-{self.issued}",
                "name": body["name"],
                "prefix": "vrn_abcd",
                "token": f"vrn_secret{self.issued}",
            }
            self.tokens[made["id"]] = {**made, "expires_at": None, "last_used_at": None, "revoked_at": None}
            return httpx.Response(201, json=made)
        if (request.method, path) == ("GET", "/auth/me"):
            me = {
                "user": {"email": "ada@example.com", "name": "Ada"},
                "organizations": [{"name": "Ada's workspace", "role": "owner"}],
            }
            return httpx.Response(200, json=me)
        if (request.method, path) == ("GET", "/auth/tokens"):
            return httpx.Response(200, json=list(self.tokens.values()))
        if request.method == "DELETE" and path.startswith("/auth/tokens/"):
            token_id = path.rsplit("/", 1)[1]
            if token_id not in self.tokens:
                return error(404, "This API token doesn't exist.")
            del self.tokens[token_id]
            return httpx.Response(204)
        return error(404, "Not found.")


def error(status: int, message: str, **details: Any) -> httpx.Response:
    return httpx.Response(status, json={"error": {"code": "x", "message": message, "details": details}})


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> FakeVerano:
    fake = FakeVerano()
    monkeypatch.setattr(client, "TRANSPORT", httpx.MockTransport(fake))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.delenv("VERANO_API_TOKEN", raising=False)
    monkeypatch.delenv("VERANO_URL", raising=False)
    monkeypatch.delenv("VERANO_DEBUG", raising=False)
    return fake


@dataclass
class Result:
    code: int
    out: str
    err: str


Run = Callable[..., Result]


@pytest.fixture
def run(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> Run:
    def invoke(*args: str, stdin: str | None = None) -> Result:
        monkeypatch.setattr(sys, "argv", ["verano", *args])
        if stdin is not None:
            monkeypatch.setattr(sys, "stdin", io.StringIO(stdin))
        code = 0
        try:
            main()
        except SystemExit as stop:
            code = int(stop.code or 0)
        captured = capsys.readouterr()
        return Result(code, captured.out, captured.err)

    return invoke


@pytest.fixture
def platform(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> "FakePlatform":
    from tests.platform import FakePlatform

    fake = FakePlatform()
    fake.tokens["t"] = {"id": "t", "token": "vrn_ci"}
    monkeypatch.setattr(client, "TRANSPORT", httpx.MockTransport(fake))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("VERANO_API_TOKEN", "vrn_ci")
    monkeypatch.setenv("VERANO_URL", "http://verano.test")
    monkeypatch.delenv("VERANO_DEBUG", raising=False)
    monkeypatch.chdir(tmp_path)
    return fake
