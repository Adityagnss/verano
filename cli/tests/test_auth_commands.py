"""`verano login`, `logout`, `whoami` and `token ...` against a fake server."""

import json
import os
import stat
import sys
from pathlib import Path

import httpx
import pytest

from tests.conftest import FakeVerano, Result, Run, error
from verano.config import credentials_path

PASSWORD = "correct horse battery"


def saved() -> dict[str, str]:
    data: dict[str, str] = json.loads(credentials_path().read_text())
    return data


def login(run: Run, *extra: str, password: str = PASSWORD) -> Result:
    return run("login", "--email", "ada@example.com", "--password-stdin", *extra, stdin=password + "\n")


def test_version(run: Run) -> None:
    result = run("--version")
    assert result.code == 0
    assert result.out.startswith("verano ")


def test_login_makes_a_token_saves_it_privately_and_ends_the_browser_style_session(
    server: FakeVerano, run: Run
) -> None:
    result = login(run)
    assert result.code == 0
    assert "Signed in as ada@example.com" in result.err
    assert result.out == ""
    assert server.calls == [("POST", "/auth/login"), ("POST", "/auth/tokens"), ("DELETE", "/auth/refresh")]
    assert saved() == {
        "url": "http://localhost:8080",
        "token": "vrn_secret1",
        "email": "ada@example.com",
        "token_id": "tok-1",
    }
    assert server.bodies[1]["expires_in_days"] == 90
    assert server.bodies[1]["name"].startswith("CLI on ")
    if sys.platform != "win32":
        assert stat.S_IMODE(os.stat(credentials_path()).st_mode) == 0o600


def test_signing_in_again_revokes_the_token_it_replaces(server: FakeVerano, run: Run) -> None:
    login(run)
    login(run, "--days", "30")
    assert list(server.tokens) == ["tok-2"]
    assert saved()["token_id"] == "tok-2"
    assert server.bodies[-3]["expires_in_days"] == 30 or any(
        b and b.get("expires_in_days") == 30 for b in server.bodies
    )


def test_a_wrong_password_saves_nothing_and_says_so(server: FakeVerano, run: Run) -> None:
    result = login(run, password="nope")
    assert result.code == 1
    assert "don't match an account" in result.err
    assert not credentials_path().exists()
    assert server.calls == [("POST", "/auth/login")]


def test_an_empty_password_is_refused_before_anything_is_sent(server: FakeVerano, run: Run) -> None:
    result = login(run, password="")
    assert result.code == 1
    assert "password is empty" in result.err
    assert server.calls == []


def test_a_server_that_is_down_is_named_with_a_hint(server: FakeVerano, run: Run) -> None:
    server.down = True
    result = login(run, "--url", "http://verano.test:9")
    assert result.code == 1
    assert "Can't reach Verano at http://verano.test:9" in result.err
    assert "docker compose up" in result.err


def test_the_wrong_address_is_recognised_when_a_web_page_answers(server: FakeVerano, run: Run) -> None:
    server.html = True
    result = login(run)
    assert result.code == 1
    assert "doesn't look like a Verano server" in result.err


def test_a_bad_address_is_caught_before_any_request(server: FakeVerano, run: Run) -> None:
    result = login(run, "--url", "localhost:8080")
    assert result.code == 1
    assert "not a server address" in result.err
    assert server.calls == []


def test_a_token_you_already_have_is_checked_before_it_is_saved(server: FakeVerano, run: Run) -> None:
    bad = run("login", "--token", "vrn_wrong")
    assert bad.code == 1
    assert "invalid, expired or revoked" in bad.err
    assert not credentials_path().exists()
    server.tokens["t"] = {"id": "t", "token": "vrn_mine"}
    good = run("login", "--token", " vrn_mine ")
    assert good.code == 0
    assert saved()["token"] == "vrn_mine"


def test_whoami_needs_a_sign_in_and_then_shows_server_and_workspace(server: FakeVerano, run: Run) -> None:
    out = run("whoami")
    assert out.code == 1
    assert "not signed in" in out.err
    assert "verano login" in out.err
    login(run)
    shown = run("whoami")
    assert shown.code == 0
    assert "Ada <ada@example.com>" in shown.out
    assert "Server:    http://localhost:8080" in shown.out
    assert "Ada's workspace (owner)" in shown.out


def test_an_expired_token_says_to_sign_in_again(server: FakeVerano, run: Run) -> None:
    login(run)
    server.tokens.clear()
    result = run("whoami")
    assert result.code == 1
    assert "invalid, expired or revoked" in result.err
    assert "verano login" in result.err


def test_ci_signs_in_through_the_environment_alone(
    server: FakeVerano, run: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    server.tokens["t"] = {"id": "t", "token": "vrn_ci"}
    monkeypatch.setenv("VERANO_API_TOKEN", "vrn_ci")
    monkeypatch.setenv("VERANO_URL", "https://verano.example.com/")
    result = run("whoami")
    assert result.code == 0
    assert "through VERANO_API_TOKEN" in result.out
    assert "Server:    https://verano.example.com" in result.out
    assert not credentials_path().exists()
    logout = run("logout")
    assert logout.code == 0
    assert "Unset it" in logout.err


def test_logout_revokes_the_token_and_deletes_the_file(server: FakeVerano, run: Run) -> None:
    login(run)
    result = run("logout")
    assert result.code == 0
    assert "The token was revoked" in result.err
    assert server.tokens == {}
    assert not credentials_path().exists()
    assert "not signed in" in run("logout").err


def test_logout_still_clears_this_machine_when_the_server_cannot_be_reached(server: FakeVerano, run: Run) -> None:
    login(run)
    server.down = True
    result = run("logout")
    assert result.code == 0
    assert "could not be revoked on the server" in result.err
    assert not credentials_path().exists()


def test_a_token_for_ci_is_printed_alone_on_standard_output(server: FakeVerano, run: Run) -> None:
    result = run(
        "token",
        "create",
        "--name",
        "ci",
        "--email",
        "ada@example.com",
        "--password-stdin",
        "--never-expires",
        stdin=PASSWORD + "\n",
    )
    assert result.code == 0
    assert result.out == "vrn_secret1\n"
    assert "VERANO_API_TOKEN" in result.err
    assert server.bodies[1] == {"name": "ci", "expires_in_days": None}
    assert not credentials_path().exists()


def test_listing_and_revoking_tokens(server: FakeVerano, run: Run) -> None:
    login(run)
    server.tokens["tok-9"] = {
        "id": "tok-9",
        "prefix": "vrn_zzzz",
        "name": "ci",
        "token": "vrn_other",
        "expires_at": "2027-01-01T00:00:00Z",
        "last_used_at": None,
        "revoked_at": None,
    }
    listed = run("token", "list")
    assert listed.code == 0
    assert "tok-9  vrn_zzzz…  ci  (expires 2027-01-01, never used)" in listed.out
    assert run("token", "revoke", "tok-9").code == 0
    missing = run("token", "revoke", "tok-9")
    assert missing.code == 1
    assert "doesn't exist" in missing.err


@pytest.mark.parametrize(
    ("response", "needle"),
    [
        (
            httpx.Response(429, headers={"retry-after": "7"}, json={"error": {"message": "Too many attempts."}}),
            "7 seconds",
        ),
        (httpx.Response(500, json={"error": {"message": "boom"}}), "docker compose logs backend"),
        (error(422, "Check the form.", fields=[{"field": "name", "message": "too long"}]), "name: too long"),
    ],
)
def test_server_errors_are_turned_into_messages_a_person_can_act_on(
    server: FakeVerano, run: Run, response: httpx.Response, needle: str
) -> None:
    login(run)
    server.fail_with[("GET", "/auth/tokens")] = response
    result = run("token", "list")
    assert result.code == 1
    assert needle in result.err
    assert "Traceback" not in result.err


def test_an_unexpected_failure_is_a_short_message_unless_debugging(
    server: FakeVerano, run: Run, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    credentials_path().parent.mkdir(parents=True)
    credentials_path().write_text("{broken")
    result = run("whoami")
    assert result.code == 1
    assert "can't be read" in result.err
    assert "Traceback" not in result.err
