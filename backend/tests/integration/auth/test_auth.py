"""Integration tests for sign-up, sessions, refresh-token rotation, revocation and login timing safety."""

import httpx
import pytest
from argon2 import PasswordHasher, extract_parameters

from app.core.container import Container
from tests.helpers import PASSWORD, sign_up

pytestmark = [pytest.mark.integration, pytest.mark.auth]

REFRESH = "/api/v1/auth/refresh"
COOKIE = "verano_refresh"


async def refresh_with(client: httpx.AsyncClient, token: str) -> httpx.Response:
    client.cookies.clear()
    return await client.post(REFRESH, headers={"Cookie": f"{COOKIE}={token}"})


async def test_signup_creates_a_personal_workspace_and_a_locked_down_refresh_cookie(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/signup", json={"email": "Ada@Example.com", "password": PASSWORD, "name": "Ada"}
    )
    assert response.status_code == 201
    cookie = response.headers["set-cookie"].lower()
    assert all(part in cookie for part in ("httponly", "secure", "samesite=strict", f"path={REFRESH}"))
    assert COOKIE not in response.text
    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {response.json()['access_token']}"})
    assert me.json()["user"]["email"] == "ada@example.com"
    [workspace] = me.json()["organizations"]
    assert (workspace["is_personal"], workspace["role"]) == (True, "owner")


async def test_refresh_rotates_the_token_and_reusing_an_old_one_revokes_the_whole_chain(
    client: httpx.AsyncClient,
) -> None:
    await sign_up(client, "rotate@example.com")
    first = client.cookies[COOKIE]
    rotated = await refresh_with(client, first)
    assert rotated.status_code == 200
    second = rotated.cookies[COOKIE]
    assert second != first

    reused = await refresh_with(client, first)
    assert reused.status_code == 401
    assert reused.json()["error"]["details"] == {"reason": "reused"}
    assert (await refresh_with(client, second)).status_code == 401


async def test_logout_revokes_the_session_and_clears_the_cookie(client: httpx.AsyncClient) -> None:
    await sign_up(client, "logout@example.com")
    token = client.cookies[COOKIE]
    logout = await client.delete(REFRESH)
    assert logout.status_code == 204
    assert 'verano_refresh=""' in logout.headers["set-cookie"] or "max-age=0" in logout.headers["set-cookie"].lower()
    assert (await refresh_with(client, token)).status_code == 401


async def test_wrong_password_and_unknown_email_get_the_same_answer(client: httpx.AsyncClient) -> None:
    await sign_up(client, "known@example.com")
    wrong = await client.post("/api/v1/auth/login", json={"email": "known@example.com", "password": "not the password"})
    unknown = await client.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": PASSWORD})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert (
        await client.post("/api/v1/auth/login", json={"email": "KNOWN@example.com", "password": PASSWORD})
    ).status_code == 200


async def test_protected_routes_require_a_valid_access_token(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/v1/auth/me")).status_code == 401
    forged = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not.a.token"})
    assert forged.status_code == 401
    assert forged.json()["error"]["code"] == "authentication_failed"


class CountingHasher:
    def __init__(self, real: PasswordHasher) -> None:
        self.real = real
        self.verified: list[str] = []

    def verify(self, hash_: str, password: str) -> bool:
        self.verified.append(hash_)
        return self.real.verify(hash_, password)


async def test_unknown_email_costs_the_same_argon2_work_as_a_wrong_password(
    client: httpx.AsyncClient, container: Container, monkeypatch: pytest.MonkeyPatch
) -> None:
    await sign_up(client, "timing@example.com")
    hasher = CountingHasher(container.passwords._hasher)
    monkeypatch.setattr(container.passwords, "_hasher", hasher)
    for email in ("timing@example.com", "ghost@example.com"):
        response = await client.post("/api/v1/auth/login", json={"email": email, "password": "not the password"})
        assert response.status_code == 401

    real_hash, dummy_hash = hasher.verified
    assert real_hash != dummy_hash
    assert extract_parameters(real_hash) == extract_parameters(dummy_hash)
