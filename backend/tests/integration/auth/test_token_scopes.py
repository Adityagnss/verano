"""Integration tests for API token scopes (read-only, one project) and for replacing a provider key (S8.1 to S8.3)."""

import logging
from collections.abc import Iterator

import httpx
import pytest
import respx
from sqlalchemy import select

from app.core.container import Container
from app.modules.registry.models import ProviderCredential
from tests.helpers import Session, add_credential, base, provider_fixture

pytestmark = [pytest.mark.integration, pytest.mark.auth]

TOKENS = "/api/v1/auth/tokens"


async def make_token(client: httpx.AsyncClient, session: Session, **body: object) -> dict[str, str]:
    response = await client.post(TOKENS, json={"name": "ci", **body}, headers=session.headers)
    assert response.status_code == 201, response.text
    created: dict[str, str] = response.json()
    return created


def bearer(token: dict[str, str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {token['token']}"}


async def test_a_read_token_can_look_and_fetch_but_is_refused_on_every_write(
    client: httpx.AsyncClient, session: Session
) -> None:
    created = await client.post(
        f"{base(session)}/prompts", json={"name": "Triage", "user_template": "Hi {{ x }}"}, headers=session.headers
    )
    prompt = created.json()
    token = await make_token(client, session, scope="read")
    assert token["scope"] == "read"
    headers = bearer(token)

    assert (await client.get(f"{base(session)}/prompts", headers=headers)).status_code == 200
    fetched = await client.get(f"{base(session)}/prompt-by-name/Triage", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["version"] == 1

    refused = [
        await client.post(f"{base(session)}/prompts", json={"name": "Other", "user_template": "x"}, headers=headers),
        await client.post(
            f"{base(session)}/prompts/{prompt['id']}/versions", json={"user_template": "y"}, headers=headers
        ),
        await client.put(
            f"{base(session)}/prompts/{prompt['id']}/labels/production",
            json={"version_id": prompt["latest_version"]["id"]},
            headers=headers,
        ),
        await client.delete(f"{base(session)}/prompts/{prompt['id']}/labels/production", headers=headers),
        await client.post(f"{base(session)}/experiments", json={"models": []}, headers=headers),
    ]
    for response in refused:
        assert response.status_code == 403, response.text
        assert "read-only" in response.json()["error"]["message"]
    # nothing changed
    listed = (await client.get(f"{base(session)}/prompts", headers=session.headers)).json()["items"]
    assert [p["name"] for p in listed] == ["Triage"]


async def test_a_project_token_gets_not_found_for_any_other_project(
    client: httpx.AsyncClient, session: Session
) -> None:
    other = await client.post("/api/v1/projects", json={"name": "Second"}, headers=session.headers)
    other_id = other.json()["id"]
    token = await make_token(client, session, scope="read", project_id=str(session.project_id))
    assert token["project_id"] == str(session.project_id)
    headers = bearer(token)
    assert (await client.get(f"{base(session)}/prompts", headers=headers)).status_code == 200
    hidden = await client.get(f"/api/v1/projects/{other_id}/prompts", headers=headers)
    assert hidden.status_code == 404
    unbound = await make_token(client, session, scope="read")
    assert (await client.get(f"/api/v1/projects/{other_id}/prompts", headers=bearer(unbound))).status_code == 200


async def test_a_token_for_a_project_you_cannot_open_is_refused(client: httpx.AsyncClient, session: Session) -> None:
    import uuid

    refused = await client.post(TOKENS, json={"name": "x", "project_id": str(uuid.uuid4())}, headers=session.headers)
    assert refused.status_code == 404, refused.text


@pytest.fixture
def providers() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as mock:
        yield mock


async def test_replacing_a_key_checks_the_new_one_first_and_never_leaks_it(
    client: httpx.AsyncClient,
    session: Session,
    providers: respx.MockRouter,
    container: Container,
    caplog: pytest.LogCaptureFixture,
) -> None:
    old, new = "sk-test-0123456789abcdefghij-1111", "sk-test-0123456789abcdefghij-2222"
    models = httpx.Response(200, json=provider_fixture("openai", "models.json"))
    route = providers.get("https://api.openai.com/v1/models")
    route.mock(models)
    credential = await add_credential(client, session, "openai", api_key=old)
    url = f"{base(session)}/credentials/{credential['id']}"

    route.mock(httpx.Response(401, json=provider_fixture("openai", "auth_error.json")))
    rejected = await client.patch(url, json={"api_key": "sk-bad-0000000000000000"}, headers=session.headers)
    assert rejected.status_code == 400
    assert (await client.get(f"{base(session)}/credentials", headers=session.headers)).json()[0]["key_last4"] == "1111"

    route.mock(models)
    caplog.set_level(logging.DEBUG)
    rotated = await client.patch(url, json={"api_key": new}, headers=session.headers)
    assert rotated.status_code == 200, rotated.text
    assert rotated.json()["key_last4"] == "2222"
    assert rotated.json()["status"] == "valid"
    assert new not in rotated.text
    assert new not in caplog.text
    async with container.database.sessions() as db:
        row = (await db.scalars(select(ProviderCredential))).one()
    assert row.encrypted_key is not None
    assert container.secret_box.decrypt(row.encrypted_key) == new
    blank = await client.patch(url, json={"api_key": "   "}, headers=session.headers)
    assert blank.status_code in (400, 422)
    label_only = await client.patch(url, json={"label": "prod"}, headers=session.headers)
    assert label_only.json()["label"] == "prod"
    assert label_only.json()["key_last4"] == "2222"
