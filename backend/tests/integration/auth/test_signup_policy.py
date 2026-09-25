"""Integration tests for auth throttling (per IP, per email, behind proxies) and the open sign-up switch."""

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

import httpx
import pytest
from fastapi import FastAPI

from app.core.container import Container
from tests.helpers import PASSWORD, sign_up

pytestmark = [pytest.mark.integration, pytest.mark.auth]

ClientFactory = Callable[[str], AbstractAsyncContextManager[httpx.AsyncClient]]


@pytest.fixture
def from_ip(app: FastAPI, clean: None) -> ClientFactory:
    @asynccontextmanager
    async def factory(ip: str) -> AsyncIterator[httpx.AsyncClient]:
        transport = httpx.ASGITransport(app=app, client=(ip, 40000))
        async with httpx.AsyncClient(transport=transport, base_url="https://verano.test") as http:
            yield http

    return factory


async def login(client: httpx.AsyncClient, email: str) -> httpx.Response:
    return await client.post("/api/v1/auth/login", json={"email": email, "password": "wrong password!"})


async def test_login_is_throttled_per_email_even_when_the_attacker_changes_ip(from_ip: ClientFactory) -> None:
    async with from_ip("10.0.0.1") as first:
        await sign_up(first, "victim@example.com")
    for attempt in range(4):
        async with from_ip(f"10.0.1.{attempt}") as client:
            assert (await login(client, "victim@example.com")).status_code == 401
    async with from_ip("10.0.2.1") as client:
        blocked = await login(client, "victim@example.com")
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "too_many_requests"
    assert int(blocked.headers["retry-after"]) > 0


async def test_one_ip_is_throttled_across_many_different_emails(from_ip: ClientFactory) -> None:
    async with from_ip("10.9.9.9") as client:
        statuses = [(await login(client, f"probe{n}@example.com")).status_code for n in range(11)]
    assert statuses == [401] * 10 + [429]


async def test_with_signup_off_only_the_first_account_can_be_created(
    client: httpx.AsyncClient, container: Container, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(container.settings, "allow_signup", False)
    assert (await client.get("/api/v1/auth/config")).json()["signup_open"] is True
    await sign_up(client, "admin@example.com")

    assert (await client.get("/api/v1/auth/config")).json()["signup_open"] is False
    stranger = await client.post(
        "/api/v1/auth/signup", json={"email": "stranger@example.com", "password": PASSWORD, "name": "Eve"}
    )
    assert stranger.status_code == 403
    assert "Sign-up is turned off" in stranger.json()["error"]["message"]
    assert (
        await client.post("/api/v1/auth/login", json={"email": "admin@example.com", "password": PASSWORD})
    ).status_code == 200


async def logins_from(app: FastAPI, peer: str, forwarded: list[str]) -> list[int]:
    transport = httpx.ASGITransport(app=app, client=(peer, 40000))
    async with httpx.AsyncClient(transport=transport, base_url="https://verano.test") as http:
        return [
            (
                await http.post(
                    "/api/v1/auth/login",
                    json={"email": f"user{n}@example.com", "password": "wrong password!"},
                    headers={"X-Forwarded-For": ip},
                )
            ).status_code
            for n, ip in enumerate(forwarded)
        ]


async def test_a_spoofed_forwarded_for_from_an_untrusted_peer_does_not_escape_the_ip_limit(
    app: FastAPI, clean: None, container: Container, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(container.settings, "trusted_proxies", ["10.0.0.0/8"])
    fake_ips = [f"198.51.100.{n}" for n in range(11)]
    assert await logins_from(app, "203.0.113.9", fake_ips) == [401] * 10 + [429]


async def test_behind_a_trusted_proxy_each_real_client_gets_its_own_limit(
    app: FastAPI, clean: None, container: Container, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(container.settings, "trusted_proxies", ["10.0.0.0/8"])
    assert await logins_from(app, "10.0.0.2", [f"198.51.100.{n}" for n in range(11)]) == [401] * 11
    assert await logins_from(app, "10.0.0.2", ["198.51.100.200"] * 11) == [401] * 10 + [429]
