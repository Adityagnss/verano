"""Integration tests: session refresh has its own generous limit and does not count towards the sign-in limits."""

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

import httpx
import pytest
from fastapi import FastAPI

from app.core.container import Container
from tests.helpers import sign_up

pytestmark = [pytest.mark.integration, pytest.mark.auth]

ClientFactory = Callable[[str], AbstractAsyncContextManager[httpx.AsyncClient]]
REFRESH = "/api/v1/auth/refresh"
COOKIE = "verano_refresh"


@pytest.fixture
def from_ip(app: FastAPI, clean: None) -> ClientFactory:
    @asynccontextmanager
    async def factory(ip: str) -> AsyncIterator[httpx.AsyncClient]:
        transport = httpx.ASGITransport(app=app, client=(ip, 40000))
        async with httpx.AsyncClient(transport=transport, base_url="https://verano.test") as http:
            yield http

    return factory


async def wrong_login(client: httpx.AsyncClient, email: str) -> httpx.Response:
    return await client.post("/api/v1/auth/login", json={"email": email, "password": "wrong password!"})


async def rotate(client: httpx.AsyncClient, token: str, forwarded: str | None = None) -> httpx.Response:
    client.cookies.clear()
    headers = {"Cookie": f"{COOKIE}={token}"}
    if forwarded:
        headers["X-Forwarded-For"] = forwarded
    return await client.post(REFRESH, headers=headers)


async def test_normal_use_refreshes_far_more_often_than_the_sign_in_limit_allows(
    from_ip: ClientFactory, container: Container, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every page load refreshes the session; an office behind one IP must not be signed out for it."""
    monkeypatch.setattr(container.settings, "auth_rate_limit_per_ip", 20)
    async with from_ip("203.0.113.50") as client:
        await sign_up(client, "busy@example.com")
        token = client.cookies.get(COOKIE)
        assert token
        for _ in range(25):
            response = await rotate(client, token)
            assert response.status_code == 200, response.text
            token = response.cookies.get(COOKIE) or ""
            assert token


async def test_refresh_has_its_own_limit_that_a_forged_forwarded_for_cannot_escape(
    from_ip: ClientFactory, container: Container, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(container.settings, "auth_refresh_rate_limit_per_ip", 3)
    monkeypatch.setattr(container.settings, "trusted_proxies", ["10.0.0.0/8"])
    async with from_ip("203.0.113.60") as client:
        await sign_up(client, "forger@example.com")
        token = client.cookies.get(COOKIE)
        assert token
        statuses = []
        for n in range(4):
            response = await rotate(client, token, forwarded=f"198.51.100.{n}")
            statuses.append(response.status_code)
            token = response.cookies.get(COOKIE) or token
        assert statuses == [200, 200, 200, 429]


async def test_twenty_one_wrong_sign_ins_from_one_ip_are_throttled_at_the_default_limit(
    from_ip: ClientFactory, container: Container, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(container.settings, "auth_rate_limit_per_ip", 20)
    async with from_ip("203.0.113.70") as client:
        statuses = [(await wrong_login(client, f"guess{n}@example.com")).status_code for n in range(21)]
    assert statuses == [401] * 20 + [429]
