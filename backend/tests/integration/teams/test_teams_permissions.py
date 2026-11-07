"""
S8.10: one permission table. Every route of the API maps to a permission; the four roles see the right things;
API token scopes limit what a token may do; people outside a workspace learn nothing about it.
"""

import uuid
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from app.core.permissions import required_role
from tests.helpers import sign_up
from tests.integration.teams.conftest import Team

pytestmark = [pytest.mark.integration, pytest.mark.auth]

NOBODY = uuid.UUID(int=7)


def test_every_route_of_the_api_has_a_permission(app: FastAPI) -> None:
    assert app.state.permission_gaps == []
    paths = app.openapi()["paths"]
    assert len(paths) > 100  # the check really looked at the whole API
    for path, methods in paths.items():
        for method in methods:
            template = path.removeprefix("/api/v1")
            if path.startswith("/api/v1"):
                required_role(method, template)  # raises UnmappedRoute for a route nobody decided about


async def status_of(client: httpx.AsyncClient, method: str, url: str, headers: dict[str, str], **kw: Any) -> int:
    return (await client.request(method, url, headers=headers, **kw)).status_code


async def test_the_viewer_reads_but_cannot_run_change_keys_or_delete(client: httpx.AsyncClient, team: Team) -> None:
    viewer = team.h("viewer")
    assert await status_of(client, "GET", f"{team.proj}/prompts", viewer) == 200
    assert await status_of(client, "GET", f"{team.proj}/experiments", viewer) == 200
    assert await status_of(client, "GET", f"{team.proj}/credentials", viewer) == 200
    assert await status_of(client, "GET", f"{team.base}/members", viewer) == 200
    for method, path, body in [
        ("POST", f"{team.proj}/experiments", {}),
        ("POST", f"{team.proj}/prompts", {"name": "x", "user_template": "hi"}),
        ("POST", f"{team.proj}/credentials", {"provider": "mock"}),
        ("DELETE", f"{team.proj}/input-files/{NOBODY}", None),
        ("DELETE", f"{team.proj}/credentials/{NOBODY}", None),
        ("POST", f"{team.proj}/llm-calls", {}),
    ]:
        response = await client.request(method, path, json=body, headers=viewer)
        assert response.status_code == 403, (method, path, response.text)
        assert "Your role in this workspace (viewer)" in response.json()["error"]["message"]


async def test_each_role_reaches_exactly_the_actions_its_rank_allows(client: httpx.AsyncClient, team: Team) -> None:
    # (method, path, body, lowest role that is allowed in)
    matrix: list[tuple[str, str, Any, str]] = [
        ("GET", f"{team.proj}/prompts", None, "viewer"),
        ("GET", f"{team.base}/members", None, "viewer"),
        ("GET", f"{team.base}/keys", None, "member"),
        ("GET", f"{team.base}/guardrails", None, "member"),
        ("GET", f"{team.base}/audit-log", None, "admin"),
        ("PUT", f"{team.base}/guardrails", {"monthly_spend_limit": None}, "admin"),
        ("POST", f"{team.proj}/credentials", {"provider": "mock"}, "admin"),
        ("POST", f"{team.proj}/prompts", {"name": "P", "user_template": "hi {{ x }}"}, "member"),
        ("POST", f"{team.proj}/experiments", {}, "member"),  # invalid body: allowed in means 422, not 403
        ("DELETE", f"{team.proj}/input-files/{NOBODY}", None, "member"),  # unknown id: allowed in means 404
    ]
    ranks = ["viewer", "member", "admin", "owner"]
    for method, path, body, lowest in matrix:
        for role in ranks:
            response = await client.request(method, path, json=body, headers=team.h(role))
            allowed = ranks.index(role) >= ranks.index(lowest)
            assert (response.status_code != 403) is allowed, (method, path, role, response.status_code, response.text)


async def test_a_member_can_start_a_run_but_not_add_a_key(client: httpx.AsyncClient, team: Team) -> None:
    member = team.h("member")
    run = await client.post(f"{team.proj}/experiments", json={}, headers=member)
    assert run.status_code == 422  # the permission passed; only the empty request is wrong
    key = await client.post(f"{team.proj}/credentials", json={"provider": "mock"}, headers=member)
    assert key.status_code == 403
    admin = await client.post(f"{team.proj}/credentials", json={"provider": "mock"}, headers=team.h("admin"))
    assert admin.status_code == 201, admin.text


async def test_somebody_outside_the_workspace_gets_not_found_never_forbidden(
    client: httpx.AsyncClient, team: Team
) -> None:
    stranger = await sign_up(client, "stranger@example.com")
    assert await status_of(client, "GET", f"{team.proj}/prompts", stranger) == 404
    assert await status_of(client, "GET", f"{team.base}/members", stranger) == 404
    assert await status_of(client, "POST", f"{team.proj}/experiments", stranger, json={}) == 404


async def test_a_read_token_can_read_but_not_write_and_a_write_token_can_do_both(
    client: httpx.AsyncClient, team: Team
) -> None:
    read = (await client.post("/api/v1/auth/tokens", json={"name": "ro", "scope": "read"}, headers=team.headers)).json()
    write = (
        await client.post("/api/v1/auth/tokens", json={"name": "rw", "scope": "write"}, headers=team.headers)
    ).json()
    assert read["scope"] == "read"
    ro, rw = {"Authorization": f"Bearer {read['token']}"}, {"Authorization": f"Bearer {write['token']}"}
    assert await status_of(client, "GET", f"{team.proj}/prompts", ro) == 200
    refused = await client.post(f"{team.proj}/prompts", json={"name": "P", "user_template": "hi"}, headers=ro)
    assert refused.status_code == 403
    assert "read-only" in refused.json()["error"]["message"]
    assert await status_of(client, "POST", f"{team.proj}/prompts", rw, json={"name": "P", "user_template": "hi"}) == 201


async def test_the_default_token_scope_is_read_only_or_write_as_documented(
    client: httpx.AsyncClient, team: Team
) -> None:
    made = (await client.post("/api/v1/auth/tokens", json={"name": "default"}, headers=team.headers)).json()
    listed = (await client.get("/api/v1/auth/tokens", headers=team.headers)).json()
    assert listed[0]["scope"] == made["scope"]
    assert made["scope"] in {"read", "write"}
    bad = await client.post("/api/v1/auth/tokens", json={"name": "x", "scope": "root"}, headers=team.headers)
    assert bad.status_code == 422
