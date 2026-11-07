"""
S8.10 (who may hand out which role) and S8.11 (invites, email verification): roles can't be raised past the
actor's own, a workspace always keeps one owner, an invite link works once, for one email, until it expires.
"""

import uuid
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import update

from app.core.container import Container
from app.core.mail import Mailer
from app.core.security import utcnow
from app.modules.auth.models import Invite
from tests.helpers import sign_up
from tests.integration.teams.conftest import Team

pytestmark = [pytest.mark.integration, pytest.mark.auth]


async def invite(
    client: httpx.AsyncClient, team: Team, email: str, role: str = "member", by: str = "owner"
) -> httpx.Response:
    return await client.post(f"{team.base}/invites", json={"email": email, "role": role}, headers=team.h(by))


def token_of(link: str) -> str:
    return link.rsplit("/", 1)[-1]


async def accept(client: httpx.AsyncClient, link: str, headers: dict[str, str]) -> httpx.Response:
    return await client.post(f"/api/v1/auth/invites/{token_of(link)}/accept", headers=headers)


async def role_of(client: httpx.AsyncClient, team: Team, role: str) -> str | None:
    members = (await client.get(f"{team.base}/members", headers=team.headers)).json()
    return next((m["role"] for m in members if m["user_id"] == str(team.users[role])), None)


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch, container: Container) -> list[tuple[str, str, str]]:
    """Email switched on, with a sender that records instead of connecting anywhere."""
    box: list[tuple[str, str, str]] = []

    async def send(self: Mailer, to: str, subject: str, body: str) -> bool:
        box.append((to, subject, body))
        return True

    monkeypatch.setattr(container.settings, "smtp_host", "smtp.test")
    monkeypatch.setattr(Mailer, "send", send)
    return box


# --- roles ---------------------------------------------------------------------------------------------


async def test_an_admin_can_only_hand_out_member_and_viewer(client: httpx.AsyncClient, team: Team) -> None:
    for role in ("owner", "admin"):
        refused = await invite(client, team, f"x-{role}@example.com", role, by="admin")
        assert refused.status_code == 403
        assert "Ask an owner" in refused.json()["error"]["message"]
    for role in ("member", "viewer"):
        assert (await invite(client, team, f"y-{role}@example.com", role, by="admin")).status_code == 201
    assert (await invite(client, team, "z-admin@example.com", "admin", by="owner")).status_code == 201

    url = f"{team.base}/members/{team.users['viewer']}"
    assert (await client.patch(url, json={"role": "admin"}, headers=team.h("admin"))).status_code == 403
    assert (await client.patch(url, json={"role": "owner"}, headers=team.h("admin"))).status_code == 403
    assert (await client.patch(url, json={"role": "member"}, headers=team.h("admin"))).status_code == 204
    assert await role_of(client, team, "viewer") == "member"


async def test_an_admin_cannot_change_or_remove_an_owner_or_another_admin(
    client: httpx.AsyncClient, team: Team
) -> None:
    for target in ("owner", "admin"):
        url = f"{team.base}/members/{team.users[target]}"
        assert (await client.patch(url, json={"role": "viewer"}, headers=team.h("admin"))).status_code == 403
        assert (await client.delete(url, headers=team.h("admin"))).status_code == 403
    assert await role_of(client, team, "owner") == "owner"


async def test_a_member_and_a_viewer_cannot_manage_people(client: httpx.AsyncClient, team: Team) -> None:
    for role in ("member", "viewer"):
        url = f"{team.base}/members/{team.users['viewer']}"
        assert (await client.patch(url, json={"role": "member"}, headers=team.h(role))).status_code == 403
        assert (await invite(client, team, "n@example.com", by=role)).status_code == 403
        assert (await client.get(f"{team.base}/invites", headers=team.h(role))).status_code == 403


async def test_the_workspace_always_keeps_one_owner(client: httpx.AsyncClient, team: Team) -> None:
    me = f"{team.base}/members/{team.users['owner']}"
    demote = await client.patch(me, json={"role": "admin"}, headers=team.headers)
    assert demote.status_code == 403
    assert "at least one owner" in demote.json()["error"]["message"]
    remove = await client.delete(me, headers=team.headers)
    assert remove.status_code == 403
    assert await role_of(client, team, "owner") == "owner"

    # with a second owner the first may step down, and the second is then the last
    assert (
        await client.patch(f"{team.base}/members/{team.users['admin']}", json={"role": "owner"}, headers=team.headers)
    ).status_code == 204
    assert (await client.patch(me, json={"role": "member"}, headers=team.headers)).status_code == 204
    last = f"{team.base}/members/{team.users['admin']}"
    assert (await client.delete(last, headers=team.h("admin"))).status_code == 403


async def test_an_owner_can_remove_a_member_who_then_loses_access(client: httpx.AsyncClient, team: Team) -> None:
    gone = await client.delete(f"{team.base}/members/{team.users['member']}", headers=team.headers)
    assert gone.status_code == 204
    assert (await client.get(f"{team.proj}/prompts", headers=team.h("member"))).status_code == 404
    again = await client.delete(f"{team.base}/members/{team.users['member']}", headers=team.headers)
    assert again.status_code == 404


async def test_a_personal_workspace_cannot_lose_its_owner_or_invite(client: httpx.AsyncClient) -> None:
    headers = await sign_up(client, "solo@example.com")
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()
    org = me["organizations"][0]["id"]
    refused = await client.post(
        f"/api/v1/organizations/{org}/invites", json={"email": "a@example.com", "role": "member"}, headers=headers
    )
    assert refused.status_code == 409
    removed = await client.delete(f"/api/v1/organizations/{org}/members/{me['user']['id']}", headers=headers)
    assert removed.status_code == 409


# --- invites -------------------------------------------------------------------------------------------


async def test_an_invite_link_adds_the_person_with_the_invited_role_once(client: httpx.AsyncClient, team: Team) -> None:
    issued = await invite(client, team, "Newbie@Example.com", "viewer")
    assert issued.status_code == 201, issued.text
    body = issued.json()
    assert body["status"] == "open"
    assert body["email"] == "newbie@example.com"
    assert body["emailed"] is False
    link = body["link"]

    preview = (await client.get(f"/api/v1/auth/invites/{token_of(link)}")).json()
    assert preview["organization_name"] == "Acme"
    assert preview["role"] == "viewer"
    assert preview["status"] == "open"

    newbie = await sign_up(client, "newbie@example.com")
    joined = await accept(client, link, newbie)
    assert joined.status_code == 200, joined.text
    assert joined.json()["name"] == "Acme"
    assert joined.json()["role"] == "viewer"
    assert (await client.get(f"{team.proj}/prompts", headers=newbie)).status_code == 200
    assert (await client.post(f"{team.proj}/prompts", json={"name": "P"}, headers=newbie)).status_code == 403

    again = await accept(client, link, newbie)
    assert again.status_code == 410
    assert again.json()["error"]["code"] == "invite_unusable"
    listed = (await client.get(f"{team.base}/invites", headers=team.headers)).json()
    assert [i["status"] for i in listed] == ["accepted"]


async def test_the_invite_only_works_for_the_email_it_was_sent_to(client: httpx.AsyncClient, team: Team) -> None:
    link = (await invite(client, team, "right@example.com")).json()["link"]
    wrong = await sign_up(client, "wrong@example.com")
    refused = await accept(client, link, wrong)
    assert refused.status_code == 403
    assert "right@example.com" in refused.json()["error"]["message"]
    assert (await client.get(f"{team.proj}/prompts", headers=wrong)).status_code == 404
    assert (await client.get("/api/v1/auth/invites/not-a-real-token")).status_code == 404


async def test_an_expired_invite_is_refused_with_a_clear_message_and_a_new_one_works(
    client: httpx.AsyncClient, team: Team, container: Container
) -> None:
    issued = (await invite(client, team, "late@example.com")).json()
    async with container.database.sessions() as db:
        await db.execute(update(Invite).values(expires_at=utcnow() - timedelta(hours=1)))
        await db.commit()
    late = await sign_up(client, "late@example.com")
    refused = await accept(client, issued["link"], late)
    assert refused.status_code == 410
    assert "has expired" in refused.json()["error"]["message"]
    assert (await client.get(f"/api/v1/auth/invites/{token_of(issued['link'])}")).json()["status"] == "expired"
    assert (await client.get(f"{team.base}/invites", headers=team.headers)).json()[0]["status"] == "expired"

    fresh = await client.post(f"{team.base}/invites/{issued['id']}/reissue", headers=team.headers)
    assert fresh.status_code == 201, fresh.text
    assert fresh.json()["link"] != issued["link"]
    assert fresh.json()["status"] == "open"
    assert (await accept(client, fresh.json()["link"], late)).status_code == 200


async def test_reissuing_withdraws_the_old_link_and_a_withdrawn_invite_cannot_be_used(
    client: httpx.AsyncClient, team: Team
) -> None:
    first = (await invite(client, team, "pending@example.com")).json()
    second = (await client.post(f"{team.base}/invites/{first['id']}/reissue", headers=team.headers)).json()
    person = await sign_up(client, "pending@example.com")
    old = await accept(client, first["link"], person)
    assert old.status_code == 410
    assert "withdrawn" in old.json()["error"]["message"]

    revoked = await client.delete(f"{team.base}/invites/{second['id']}", headers=team.headers)
    assert revoked.status_code == 204
    assert (await accept(client, second["link"], person)).status_code == 410
    states = {i["id"]: i["status"] for i in (await client.get(f"{team.base}/invites", headers=team.headers)).json()}
    assert states == {first["id"]: "revoked", second["id"]: "revoked"}
    assert (await client.delete(f"{team.base}/invites/{uuid.uuid4()}", headers=team.headers)).status_code == 404


async def test_signing_up_through_an_invite_link_joins_the_workspace(client: httpx.AsyncClient, team: Team) -> None:
    link = (await invite(client, team, "fresh@example.com", "member")).json()["link"]
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": "fresh@example.com",
            "password": "correct horse battery",
            "name": "Fay",
            "invite_token": token_of(link),
        },
    )
    assert response.status_code == 201, response.text
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    organizations = (await client.get("/api/v1/auth/me", headers=headers)).json()["organizations"]
    assert {(o["name"], o["role"]) for o in organizations} >= {("Acme", "member")}


async def test_an_email_that_is_already_a_member_or_too_many_open_invites_are_refused(
    client: httpx.AsyncClient, team: Team, monkeypatch: pytest.MonkeyPatch, container: Container
) -> None:
    dup = await invite(client, team, team.emails["viewer"])
    assert dup.status_code == 409
    assert "already a member" in dup.json()["error"]["message"]
    monkeypatch.setattr(container.settings, "max_open_invites", 1)
    assert (await invite(client, team, "one@example.com")).status_code == 201
    assert (await invite(client, team, "two@example.com")).status_code == 409
    assert (await invite(client, team, "one@example.com")).status_code == 201  # replacing an open one is fine


# --- email: with and without SMTP ----------------------------------------------------------------------


async def test_without_smtp_the_link_is_shown_and_accepting_needs_no_verification(
    client: httpx.AsyncClient, team: Team
) -> None:
    assert (await client.get("/api/v1/auth/config")).json()["email_verification_required"] is False
    issued = (await invite(client, team, "nomail@example.com")).json()
    assert issued["emailed"] is False
    assert issued["link"].startswith("http")
    headers = await sign_up(client, "nomail@example.com")
    assert (await client.get("/api/v1/auth/me", headers=headers)).json()["user"]["email_verified"] is False
    assert (await accept(client, issued["link"], headers)).status_code == 200
    resend = await client.post("/api/v1/auth/resend-verification", headers=headers)
    assert resend.status_code == 409
    assert "isn't set up" in resend.json()["error"]["message"]


async def test_with_smtp_the_invite_is_emailed_and_following_it_proves_the_address(
    client: httpx.AsyncClient, team: Team, sent: list[tuple[str, str, str]]
) -> None:
    issued = (await invite(client, team, "mailed@example.com")).json()
    assert issued["emailed"] is True
    to, subject, body = sent[-1]
    assert to == "mailed@example.com"
    assert "Acme" in subject
    assert issued["link"] in body
    headers = await sign_up(client, "mailed@example.com")  # sign-up sends a verification email too
    assert (await accept(client, issued["link"], headers)).status_code == 200
    assert (await client.get("/api/v1/auth/me", headers=headers)).json()["user"]["email_verified"] is True


async def test_with_smtp_an_unverified_person_cannot_accept_an_invite_that_was_not_emailed(
    client: httpx.AsyncClient, team: Team, sent: list[tuple[str, str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def failing(self: Mailer, to: str, subject: str, body: str) -> bool:
        return False

    monkeypatch.setattr(Mailer, "send", failing)
    issued = (await invite(client, team, "unsent@example.com")).json()
    assert issued["emailed"] is False
    headers = await sign_up(client, "unsent@example.com")
    refused = await accept(client, issued["link"], headers)
    assert refused.status_code == 403
    assert "Verify your email" in refused.json()["error"]["message"]


async def test_the_verification_link_marks_the_address_verified_once(
    client: httpx.AsyncClient, sent: list[tuple[str, str, str]]
) -> None:
    assert (await client.get("/api/v1/auth/config")).json()["email_verification_required"] is True
    headers = await sign_up(client, "verify@example.com")
    assert (await client.get("/api/v1/auth/me", headers=headers)).json()["user"]["email_verified"] is False
    body = sent[-1][2]
    token = body.split("token=")[1].split()[0]

    assert (await client.post("/api/v1/auth/verify-email", json={"token": token})).status_code == 204
    assert (await client.get("/api/v1/auth/me", headers=headers)).json()["user"]["email_verified"] is True
    reused = await client.post("/api/v1/auth/verify-email", json={"token": token})
    assert reused.status_code == 422
    assert "isn't valid or has expired" in reused.json()["error"]["message"]
    assert (await client.post("/api/v1/auth/verify-email", json={"token": "nope"})).status_code == 422


async def test_an_unverified_person_can_ask_for_a_new_verification_email(
    client: httpx.AsyncClient, sent: list[tuple[str, str, str]]
) -> None:
    headers = await sign_up(client, "again@example.com")
    before = len(sent)
    assert (await client.post("/api/v1/auth/resend-verification", headers=headers)).status_code == 204
    assert len(sent) == before + 1
    assert sent[-1][0] == "again@example.com"


async def test_signing_up_is_not_blocked_while_the_address_is_unverified(
    client: httpx.AsyncClient, sent: list[tuple[str, str, str]]
) -> None:
    """Decision: an unverified person can sign in and use their own workspace (a lost email must not lock anyone
    out); the address only has to be proven to join someone else's workspace (see the test above)."""
    headers = await sign_up(client, "free@example.com")
    project = await client.post("/api/v1/projects", json={"name": "Mine"}, headers=headers)
    assert project.status_code == 201
