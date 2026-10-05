"""Integration tests for personal API tokens: made from a session, stored hashed, revocable, expiring."""

import uuid
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import select, update

from app.core.container import Container
from app.core.security import digest_token, utcnow
from app.modules.auth.models import ApiToken
from tests.helpers import sign_up

pytestmark = [pytest.mark.integration, pytest.mark.auth]

TOKENS = "/api/v1/auth/tokens"
INVALID = "This API token is invalid, expired or revoked."


async def make(client: httpx.AsyncClient, headers: dict[str, str], name: str = "ci", **extra: object) -> dict[str, str]:
    response = await client.post(TOKENS, json={"name": name, **extra}, headers=headers)
    assert response.status_code == 201, response.text
    created: dict[str, str] = response.json()
    return created


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_a_token_is_shown_once_stored_only_as_a_hash_and_works_like_a_session(
    client: httpx.AsyncClient, container: Container
) -> None:
    headers = await sign_up(client, "tokens@example.com")
    created = await make(client, headers, "  my laptop  ")
    token = created["token"]
    assert token.startswith("vrn_")
    assert created["prefix"] == token[:8]
    assert created["name"] == "my laptop"
    assert created["expires_at"] is not None

    listed = (await client.get(TOKENS, headers=headers)).json()
    assert [t["id"] for t in listed] == [created["id"]]
    assert "token" not in listed[0]
    assert "token_hash" not in listed[0]

    async with container.database.sessions() as db:
        row = (await db.scalars(select(ApiToken))).one()
    assert row.token_hash == digest_token(token)
    assert token not in row.token_hash

    me = await client.get("/api/v1/auth/me", headers=bearer(token))
    assert me.status_code == 200
    assert me.json()["user"]["email"] == "tokens@example.com"
    async with container.database.sessions() as db:
        assert (await db.scalars(select(ApiToken.last_used_at))).one() is not None


async def test_a_token_cannot_make_more_tokens(client: httpx.AsyncClient) -> None:
    created = await make(client, await sign_up(client, "chain@example.com"))
    response = await client.post(TOKENS, json={"name": "more"}, headers=bearer(created["token"]))
    assert response.status_code == 403
    assert (await client.get(TOKENS, headers=bearer(created["token"]))).status_code == 200


async def test_revoked_expired_and_made_up_tokens_all_get_the_same_answer(
    client: httpx.AsyncClient, container: Container
) -> None:
    headers = await sign_up(client, "gone@example.com")
    revoked, expired = await make(client, headers, "revoked"), await make(client, headers, "expired")
    assert (await client.delete(f"{TOKENS}/{revoked['id']}", headers=headers)).status_code == 204
    assert (await client.delete(f"{TOKENS}/{revoked['id']}", headers=headers)).status_code == 204
    async with container.database.sessions() as db:
        await db.execute(
            update(ApiToken).where(ApiToken.id == uuid.UUID(expired["id"])).values(expires_at=utcnow() - timedelta(1))
        )
        await db.commit()
    for token in (revoked["token"], expired["token"], "vrn_" + "x" * 43):
        response = await client.get("/api/v1/auth/me", headers=bearer(token))
        assert response.status_code == 401, token
        assert response.json()["error"]["message"] == INVALID, token
    listed = {t["name"]: t["revoked_at"] is not None for t in (await client.get(TOKENS, headers=headers)).json()}
    assert listed == {"revoked": True, "expired": False}


async def test_tokens_belong_to_their_owner(client: httpx.AsyncClient) -> None:
    ada = await sign_up(client, "ada-t@example.com")
    bo = await sign_up(client, "bo-t@example.com")
    created = await make(client, ada)
    assert (await client.get(TOKENS, headers=bo)).json() == []
    assert (await client.delete(f"{TOKENS}/{created['id']}", headers=bo)).status_code == 404
    assert (await client.delete(f"{TOKENS}/{uuid.uuid4()}", headers=bo)).status_code == 404
    assert (await client.get("/api/v1/auth/me", headers=bearer(created["token"]))).status_code == 200


async def test_the_name_and_expiry_are_checked_and_never_expiring_is_allowed(client: httpx.AsyncClient) -> None:
    headers = await sign_up(client, "rules@example.com")
    for body in (
        {"name": "   "},
        {"name": ""},
        {"name": "x" * 101},
        {"name": "a", "expires_in_days": 0},
        {"name": "a", "expires_in_days": 366},
    ):
        assert (await client.post(TOKENS, json=body, headers=headers)).status_code == 422, body
    forever = await make(client, headers, "forever", expires_in_days=None)
    assert forever["expires_at"] is None
    assert (await client.post(TOKENS, headers=headers)).status_code == 422
    assert (await client.post(TOKENS, json={"name": "a"})).status_code == 401


async def test_there_is_a_limit_on_active_tokens_and_revoking_frees_a_place(client: httpx.AsyncClient) -> None:
    headers = await sign_up(client, "limit@example.com")
    first = await make(client, headers, "t0")
    for index in range(1, 20):
        await make(client, headers, f"t{index}")
    full = await client.post(TOKENS, json={"name": "one too many"}, headers=headers)
    assert full.status_code == 409
    assert "20 active" in full.json()["error"]["message"]
    await client.delete(f"{TOKENS}/{first['id']}", headers=headers)
    await make(client, headers, "fits now")
