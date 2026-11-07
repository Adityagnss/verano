"""
Sign in with an identity provider, against a fake OpenID Connect provider written for these tests. A good sign-in
creates the person, joins them to the workspace with the role their groups map to (never above admin); every
way an answer can be wrong (state, nonce, PKCE, signature, issuer, audience, expiry, unverified email) is refused
and signs nobody in.
"""

import time
import uuid
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from sqlalchemy import select

from app.core.container import Container
from app.modules.auth import oidc
from app.modules.auth.models import ExternalIdentity, User
from tests.helpers import sign_up
from tests.integration.teams.conftest import Team
from tests.integration.teams.fake_oidc import CLIENT_ID, CLIENT_SECRET, ISSUER, FakeIdP

pytestmark = [pytest.mark.integration, pytest.mark.auth]

START = "/api/v1/auth/oidc/corp/start"
CALLBACK = "/api/v1/auth/oidc/corp/callback"


@pytest.fixture
async def idp(container: Container, team: Team, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[FakeIdP]:
    fake = FakeIdP()
    monkeypatch.setattr(container, "http", httpx.AsyncClient(transport=httpx.ASGITransport(app=fake.app)))
    monkeypatch.setattr(
        container.settings,
        "oidc_providers",
        [
            {
                "name": "corp",
                "kind": "oidc",
                "display_name": "Corp login",
                "issuer": ISSUER,
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "organization_id": str(team.organization_id),
                "default_role": "viewer",
                "roles_claim": "groups",
                "role_map": {"verano-admins": "admin", "verano-owners": "owner", "verano-members": "member"},
            }
        ],
    )
    oidc._discovery_cache.clear()
    oidc._jwks_cache.clear()
    yield fake
    await container.http.aclose()
    oidc._discovery_cache.clear()
    oidc._jwks_cache.clear()


async def begin(client: httpx.AsyncClient) -> str:
    started = await client.get(START)
    assert started.status_code == 200, started.text
    url: str = started.json()["authorization_url"]
    return url


def state_of(url: str) -> str:
    return parse_qs(urlparse(url).query)["state"][0]


async def sign_in(client: httpx.AsyncClient, idp: FakeIdP, **claims: Any) -> httpx.Response:
    url = await begin(client)
    code = idp.authorize(url, **claims)
    return await client.get(CALLBACK, params={"code": code, "state": state_of(url)})


def refused_with(response: httpx.Response) -> str:
    assert response.status_code == 303, response.text
    location = response.headers["location"]
    assert "/login?error=" in location, location
    return parse_qs(urlparse(location).query)["error"][0]


async def finished(client: httpx.AsyncClient, response: httpx.Response) -> dict[str, Any]:
    """The sign-in went through: the browser is sent on and the refresh cookie gives an access token."""
    assert response.status_code == 303, response.headers
    assert response.headers["location"].endswith("/signin/complete"), response.headers
    session = await client.post("/api/v1/auth/refresh")
    assert session.status_code == 200, session.text
    body: dict[str, Any] = session.json()
    return body


async def user_count(container: Container, email: str) -> int:
    async with container.database.sessions() as db:
        return len((await db.scalars(select(User).where(User.email == email))).all())


def role_in(me: dict[str, Any], team: Team) -> str | None:
    return next((o["role"] for o in me["organizations"] if o["id"] == str(team.organization_id)), None)


async def me_of(client: httpx.AsyncClient, session: dict[str, Any]) -> dict[str, Any]:
    response = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {session['access_token']}"})
    body: dict[str, Any] = response.json()
    return body


async def test_the_sign_in_page_lists_the_provider_and_start_sends_pkce_state_and_nonce(
    client: httpx.AsyncClient, idp: FakeIdP
) -> None:
    providers = (await client.get("/api/v1/auth/config")).json()["sign_in_providers"]
    assert providers == [{"name": "corp", "display_name": "Corp login", "kind": "oidc"}]
    url = await begin(client)
    query = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
    assert url.startswith(f"{ISSUER}/authorize?")
    assert query["code_challenge_method"] == "S256"
    assert len(query["code_challenge"]) >= 43
    assert len(query["state"]) >= 32
    assert len(query["nonce"]) >= 32
    assert query["redirect_uri"].endswith("/api/v1/auth/oidc/corp/callback")
    assert (await client.get("/api/v1/auth/oidc/nobody/start")).status_code == 404


async def test_a_good_sign_in_creates_the_person_joins_the_workspace_and_is_recorded(
    client: httpx.AsyncClient, idp: FakeIdP, team: Team, container: Container
) -> None:
    response = await sign_in(client, idp, groups=["verano-admins"])
    me = await me_of(client, await finished(client, response))
    assert me["user"]["email"] == "ada@corp.example"
    assert me["user"]["email_verified"] is True
    assert role_in(me, team) == "admin"
    assert sum(1 for o in me["organizations"] if o["is_personal"]) == 1  # and a workspace of their own
    # the code was swapped with the PKCE verifier and the client secret
    assert idp.token_requests[0]["code_verifier"]
    assert idp.token_requests[0]["client_secret"] == CLIENT_SECRET
    async with container.database.sessions() as db:
        assert (await db.scalars(select(ExternalIdentity.subject))).all() == ["subject-1"]
    admin_log = await client.get(f"{team.base}/audit-log", params={"action": "member.joined"}, headers=team.headers)
    [joined] = admin_log.json()["items"]
    assert "ada@corp.example" in joined["summary"]
    assert joined["details"]["provider"] == "corp"


async def test_a_person_with_no_matching_group_gets_the_default_role(
    client: httpx.AsyncClient, idp: FakeIdP, team: Team
) -> None:
    me = await me_of(client, await finished(client, await sign_in(client, idp, groups=["something-else"])))
    assert role_in(me, team) == "viewer"


async def test_a_role_from_the_provider_is_never_higher_than_admin(
    client: httpx.AsyncClient, idp: FakeIdP, team: Team
) -> None:
    me = await me_of(client, await finished(client, await sign_in(client, idp, groups=["verano-owners"])))
    assert role_in(me, team) == "admin"


async def test_the_role_follows_the_groups_on_the_next_sign_in_but_an_owner_is_never_demoted(
    client: httpx.AsyncClient, idp: FakeIdP, team: Team
) -> None:
    await finished(client, await sign_in(client, idp, groups=["verano-admins"]))
    me = await me_of(client, await finished(client, await sign_in(client, idp, groups=["verano-members"])))
    assert role_in(me, team) == "member"
    changed = await client.get(f"{team.base}/audit-log", params={"action": "role.changed"}, headers=team.headers)
    assert changed.json()["items"][0]["details"] == {"from": "admin", "to": "member", "provider": "corp"}

    # the workspace owner signs in through the provider with the same verified email: stays owner
    await client.delete(f"{team.base}/members/{team.users['viewer']}", headers=team.headers)
    owner_email = team.emails["owner"]
    again = await sign_in(client, idp, sub="owner-subject", email=owner_email, groups=["verano-members"])
    me = await me_of(client, await finished(client, again))
    assert me["user"]["email"] == owner_email
    assert role_in(me, team) == "owner"


async def test_an_existing_account_with_the_same_verified_email_is_linked_not_duplicated(
    client: httpx.AsyncClient, idp: FakeIdP, container: Container
) -> None:
    await sign_up(client, "ada@corp.example")
    me = await me_of(client, await finished(client, await sign_in(client, idp)))
    assert me["user"]["email"] == "ada@corp.example"
    assert await user_count(container, "ada@corp.example") == 1


async def test_a_state_that_was_never_issued_or_already_used_is_refused(
    client: httpx.AsyncClient, idp: FakeIdP, container: Container
) -> None:
    url = await begin(client)
    code = idp.authorize(url)
    forged = await client.get(CALLBACK, params={"code": code, "state": "not-a-state-we-issued"})
    assert "expired or was already used" in refused_with(forged)
    good = await client.get(CALLBACK, params={"code": code, "state": state_of(url)})
    assert good.headers["location"].endswith("/signin/complete")
    replay = await client.get(CALLBACK, params={"code": idp.authorize(url), "state": state_of(url)})
    assert "expired or was already used" in refused_with(replay)
    assert (await client.get(CALLBACK, params={"state": state_of(url)})).status_code == 303  # no code at all
    assert await user_count(container, "ada@corp.example") == 1


async def test_a_state_issued_for_one_provider_cannot_finish_another(
    client: httpx.AsyncClient, idp: FakeIdP, container: Container, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = container.settings.oidc_providers[0]
    monkeypatch.setattr(container.settings, "oidc_providers", [first, {**first, "name": "second"}])
    url = await begin(client)
    code = idp.authorize(url)
    crossed = await client.get("/api/v1/auth/oidc/second/callback", params={"code": code, "state": state_of(url)})
    assert "expired or was already used" in refused_with(crossed)


async def test_every_wrong_id_token_is_refused_and_nobody_is_created(
    client: httpx.AsyncClient, idp: FakeIdP, container: Container
) -> None:
    now = int(time.time())
    cases: list[tuple[str, dict[str, Any], str]] = [
        ("wrong nonce", {"nonce": "somebody-elses-nonce"}, "doesn't match this sign-in attempt"),
        ("wrong audience", {"aud": "another-app"}, "meant for a different app"),
        ("two audiences without azp", {"aud": [CLIENT_ID, "other"]}, "meant for a different app"),
        ("wrong issuer", {"iss": "https://evil.example"}, "unexpected provider"),
        ("expired", {"exp": now - 3600}, "has expired"),
        ("no expiry", {"exp": None}, "has expired"),
        ("email not verified", {"email_verified": False}, "isn't verified at the provider"),
        ("no verified flag", {"email_verified": None}, "isn't verified at the provider"),
        ("no email", {"email": None}, "no email address"),
        ("no subject", {"sub": None}, "could not be checked"),
    ]
    for label, claims, message in cases:
        response = await sign_in(client, idp, **claims)
        assert message in refused_with(response), label
        assert await user_count(container, "ada@corp.example") == 0, label


async def test_a_token_signed_with_the_wrong_key_is_refused(
    client: httpx.AsyncClient, idp: FakeIdP, container: Container
) -> None:
    idp.sign_with_other_key = True
    response = await sign_in(client, idp)
    assert "could not be checked" in refused_with(response)
    assert await user_count(container, "ada@corp.example") == 0


async def test_a_provider_that_refuses_or_fails_says_so_without_signing_anyone_in(
    client: httpx.AsyncClient, idp: FakeIdP, container: Container
) -> None:
    denied = await client.get(CALLBACK, params={"error": "access_denied", "state": "x"})
    assert "refused the sign-in: access_denied" in refused_with(denied)
    idp.fail_token_endpoint = True
    broken = await sign_in(client, idp)
    assert "refused the sign-in" in refused_with(broken)
    assert await user_count(container, "ada@corp.example") == 0


async def test_a_wrong_pkce_verifier_is_rejected_by_the_provider(
    client: httpx.AsyncClient, idp: FakeIdP, container: Container
) -> None:
    url = await begin(client)
    code = idp.authorize(url)
    # the provider remembers the challenge from the first start; a code tied to another start fails
    other = await begin(client)
    code_for_other = idp.authorize(other)
    idp.codes[code_for_other]["query"]["code_challenge"] = idp.codes[code]["query"]["code_challenge"]
    refused = await client.get(CALLBACK, params={"code": code_for_other, "state": state_of(other)})
    assert "code was not accepted" in refused_with(refused)
    assert await user_count(container, "ada@corp.example") == 0


async def test_only_listed_email_domains_may_sign_in_when_the_provider_lists_domains(
    client: httpx.AsyncClient, idp: FakeIdP, container: Container, monkeypatch: pytest.MonkeyPatch
) -> None:
    only = [{**container.settings.oidc_providers[0], "allowed_domains": ["other.example"]}]
    monkeypatch.setattr(container.settings, "oidc_providers", only)
    response = await sign_in(client, idp)
    assert "can't sign in here" in refused_with(response)
    assert await user_count(container, "ada@corp.example") == 0


async def test_a_closed_server_does_not_let_strangers_in_through_a_provider_that_has_no_workspace(
    client: httpx.AsyncClient, idp: FakeIdP, container: Container, monkeypatch: pytest.MonkeyPatch
) -> None:
    open_provider = {**container.settings.oidc_providers[0], "organization_id": None}
    monkeypatch.setattr(container.settings, "oidc_providers", [open_provider])
    monkeypatch.setattr(container.settings, "allow_signup", False)
    response = await sign_in(client, idp)
    assert "Sign-up is turned off" in refused_with(response)
    assert await user_count(container, "ada@corp.example") == 0
    # while a provider tied to a workspace is how that workspace's people join, so it still works
    monkeypatch.setattr(container.settings, "oidc_providers", [{**open_provider, "organization_id": str(uuid.uuid4())}])
    assert (await sign_in(client, idp)).headers["location"].endswith("/signin/complete")
