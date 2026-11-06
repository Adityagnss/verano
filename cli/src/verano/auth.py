"""Signing in and API tokens: what `login`, `logout`, `whoami` and `token ...` do."""

import contextlib
import sys
from typing import Any

import typer

from verano import ui
from verano.client import ApiClient, token_name
from verano.config import (
    DEFAULT_URL,
    Credentials,
    credentials_path,
    delete_credentials,
    load_credentials,
    normalize_url,
    save_credentials,
)
from verano.errors import CliError

NOT_SIGNED_IN = CliError("You are not signed in.", "Run `verano login`, or set VERANO_API_TOKEN (and VERANO_URL).")


def signed_in() -> Credentials:
    credentials = load_credentials()
    if credentials is None:
        raise NOT_SIGNED_IN
    return credentials


def client() -> ApiClient:
    return ApiClient.from_credentials(signed_in())


def _read_password(from_stdin: bool) -> str:
    password = sys.stdin.readline().rstrip("\r\n") if from_stdin else typer.prompt("Password", hide_input=True)
    if not password:
        raise CliError("The password is empty.")
    return password


def _known_email(url: str, password_stdin: bool) -> str:
    """The email when none was given. With the password on stdin, stdin can't also answer a
    question, so the saved sign-in for this server is used, or the user is told to pass --email."""
    if not password_stdin:
        return str(typer.prompt("Email"))
    saved = load_credentials()
    if saved and saved.email and saved.url == url:
        return saved.email
    raise CliError("--password-stdin needs --email.", "Add --email you@example.com.")


def _session(url: str, email: str | None, password_stdin: bool) -> tuple[ApiClient, ApiClient, str]:
    """Sign in with a password. Returns the anonymous client (it holds the refresh cookie), the
    signed-in one, and the account email. The browser-style session is only used to make a token."""
    email = email or _known_email(url, password_stdin)
    password = _read_password(password_stdin)
    anonymous = ApiClient(url)
    session: dict[str, Any] = anonymous.post("/auth/login", {"email": email, "password": password})
    return anonymous, ApiClient(url, session["access_token"]), str(session["user"]["email"])


def _end_session(anonymous: ApiClient) -> None:
    """Best effort: the session was only needed to make a token."""
    with contextlib.suppress(CliError):
        anonymous.delete("/auth/refresh")


def _target_url(url: str | None) -> str:
    if url:
        return normalize_url(url)
    saved = load_credentials()
    return saved.url if saved else normalize_url(DEFAULT_URL)


def login(url: str | None, email: str | None, password_stdin: bool, token: str | None, days: int) -> None:
    target = _target_url(url)
    previous = load_credentials()
    if token:
        _login_with_token(target, token.strip())
        return
    ui.info(f"Signing in to {target}")
    anonymous, authed, account = _session(target, email, password_stdin)
    try:
        created = authed.post("/auth/tokens", {"name": token_name(), "expires_in_days": days})
    finally:
        _end_session(anonymous)
    path = save_credentials(Credentials(target, created["token"], account, created["id"]))
    ui.ok(f"Signed in as {account}. Token saved to {path} (valid {days} days).")
    if previous and previous.source == "file" and previous.token_id:
        _revoke_quietly(ApiClient(target, created["token"]), previous.token_id)
    active = load_credentials()
    if active is not None and active.source == "environment":
        ui.warn("VERANO_API_TOKEN is set and takes precedence over this saved sign-in.")


def _login_with_token(url: str, token: str) -> None:
    me = ApiClient(url, token).get("/auth/me")
    account = str(me["user"]["email"])
    path = save_credentials(Credentials(url, token, account))
    ui.ok(f"Token accepted for {account}. Saved to {path}.")


def _revoke_quietly(api: ApiClient, token_id: str) -> None:
    with contextlib.suppress(CliError):
        api.delete(f"/auth/tokens/{token_id}")


def logout() -> None:
    credentials = load_credentials()
    if credentials is None:
        ui.info("You are not signed in.")
        return
    if credentials.source == "environment":
        ui.warn("You are signed in through VERANO_API_TOKEN. Unset it to sign out; nothing was changed.")
        return
    revoked = False
    if credentials.token_id:
        try:
            ApiClient.from_credentials(credentials).delete(f"/auth/tokens/{credentials.token_id}")
            revoked = True
        except CliError as error:
            ui.warn(f"The token could not be revoked on the server ({error.message}). Revoke it from the web app.")
    delete_credentials()
    ui.ok("Signed out." + (" The token was revoked." if revoked else " The saved token was deleted from this machine."))


def whoami() -> None:
    credentials = signed_in()
    me = ApiClient.from_credentials(credentials).get("/auth/me")
    user = me["user"]
    typer.echo(f"{user['name']} <{user['email']}>")
    typer.echo(f"Server:    {credentials.url}")
    where = "VERANO_API_TOKEN" if credentials.source == "environment" else str(credentials_path())
    typer.echo(f"Signed in: through {where}")
    for org in me.get("organizations", []):
        typer.echo(f"Workspace: {org['name']} ({org['role']})")


def create_token(
    name: str,
    url: str | None,
    email: str | None,
    password_stdin: bool,
    days: int | None,
    read_only: bool = False,
    project: str | None = None,
) -> None:
    target = _target_url(url)
    ui.info(f"Signing in to {target} to create the token")
    anonymous, authed, _ = _session(target, email, password_stdin)
    try:
        body: dict[str, Any] = {"name": name, "expires_in_days": days, "scope": "read" if read_only else "write"}
        if project:
            matches = [p for p in authed.pages("/projects") if p["name"] == project]
            if len(matches) != 1:
                raise CliError(
                    f'There is no single project called "{project}".', "Check the name in the web app's project list."
                )
            body["project_id"] = matches[0]["id"]
        created = authed.post("/auth/tokens", body)
    finally:
        _end_session(anonymous)
    limits = ("read-only" if read_only else "full access") + (f", only for {project}" if project else "")
    ui.ok(
        f"Token '{name}' created ({limits}; {'never expires' if days is None else f'valid {days} days'}). "
        "It is shown only now:"
    )
    typer.echo(created["token"])
    ui.info("In CI, set it as VERANO_API_TOKEN (and VERANO_URL for your server).")


def list_tokens() -> None:
    tokens = client().get("/auth/tokens")
    if not tokens:
        ui.info("No tokens yet.")
        return
    for t in tokens:
        state = (
            "revoked" if t["revoked_at"] else f"expires {t['expires_at'][:10]}" if t["expires_at"] else "never expires"
        )
        used = f"last used {t['last_used_at'][:10]}" if t["last_used_at"] else "never used"
        scope = "read-only" if t.get("scope") == "read" else "full access"
        typer.echo(f"{t['id']}  {t['prefix']}…  {t['name']}  ({scope}, {state}, {used})")


def revoke_token(token_id: str) -> None:
    client().delete(f"/auth/tokens/{token_id}")
    ui.ok("Token revoked.")
