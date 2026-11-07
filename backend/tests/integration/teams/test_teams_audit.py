"""
S8.14: the audit log. Every change that matters to a team is recorded with who did it, when and what, it can be
filtered and downloaded, only owners and admins can read it, and nothing can change or delete an entry.
"""

import csv
import io
import json
import uuid
from datetime import timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.container import Container
from app.core.jobs import InlineJobQueue
from app.core.security import utcnow
from app.modules.assistant.models import PromptCandidate
from app.modules.assistant.schemas import CandidateOutcome
from tests.helpers import Session, approved_project, base, create_prompt, judged_project, run_good
from tests.integration.teams.conftest import ProviderMock, Team

pytestmark = [pytest.mark.integration, pytest.mark.auth]

KEY = "sk-audit-0123456789abcdefghij-1234"
NEW_KEY = "sk-audit-0123456789abcdefghij-9999"


async def events(client: httpx.AsyncClient, team: Team, **query: Any) -> list[dict[str, Any]]:
    response = await client.get(f"{team.base}/audit-log", params={"limit": 200, **query}, headers=team.headers)
    assert response.status_code == 200, response.text
    items: list[dict[str, Any]] = response.json()["items"]
    return items


async def actions(client: httpx.AsyncClient, team: Team) -> list[str]:
    return [e["action"] for e in await events(client, team)]


async def test_the_log_cannot_be_changed_or_deleted_even_with_direct_database_access(
    client: httpx.AsyncClient, team: Team, container: Container
) -> None:
    await client.put(f"{team.base}/guardrails", json={"monthly_spend_limit": "10"}, headers=team.headers)
    assert await actions(client, team) == ["limit.changed"]
    for statement in ("UPDATE audit_events SET summary = 'tampered'", "DELETE FROM audit_events"):
        async with container.database.engine.begin() as connection:
            with pytest.raises(DBAPIError, match="can only be added to"):
                await connection.execute(text(statement))
    assert len(await events(client, team)) == 1
    # the API has no way to change an entry either
    for method in ("put", "patch", "delete", "post"):
        response = await getattr(client, method)(f"{team.base}/audit-log", headers=team.headers)
        assert response.status_code == 405


async def test_only_owners_and_admins_can_read_the_log(client: httpx.AsyncClient, team: Team) -> None:
    for role, expected in (("owner", 200), ("admin", 200), ("member", 403), ("viewer", 403)):
        for tail in ("", "/actions", "/export"):
            response = await client.get(f"{team.base}/audit-log{tail}", headers=team.h(role))
            assert response.status_code == expected, (role, tail)


async def test_keys_roles_members_invites_and_the_limit_are_each_recorded_with_who_and_what(
    client: httpx.AsyncClient, team: Team, provider: ProviderMock
) -> None:
    provider.valid.update({KEY, NEW_KEY})
    key = (
        await client.post(f"{team.base}/keys", json={"provider": "openai", "api_key": KEY}, headers=team.h("admin"))
    ).json()
    await client.post(
        f"{team.base}/keys/{key['id']}/projects", json={"project_id": str(team.project_id)}, headers=team.headers
    )
    await client.post(f"{team.base}/keys/{key['id']}/rotate", json={"api_key": NEW_KEY}, headers=team.headers)
    await client.patch(f"{team.base}/members/{team.users['viewer']}", json={"role": "member"}, headers=team.headers)
    invited = (
        await client.post(
            f"{team.base}/invites", json={"email": "j@example.com", "role": "viewer"}, headers=team.headers
        )
    ).json()
    await client.delete(f"{team.base}/invites/{invited['id']}", headers=team.headers)
    await client.put(f"{team.base}/guardrails", json={"monthly_spend_limit": "25.50"}, headers=team.h("admin"))
    await client.delete(f"{team.base}/members/{team.users['member']}", headers=team.headers)
    await client.delete(f"{team.base}/keys/{key['id']}/projects/{team.project_id}", headers=team.headers)
    await client.delete(f"{team.base}/keys/{key['id']}", headers=team.headers)

    log = await events(client, team)
    assert [e["action"] for e in reversed(log)] == [
        "key.added",
        "key.attached",  # the project credential made when the key was put to use
        "key.rotated",
        "role.changed",
        "invite.sent",
        "invite.revoked",
        "limit.changed",
        "member.removed",
        "key.detached",
        "key.removed",
    ]
    by_action = {e["action"]: e for e in log}
    assert by_action["key.rotated"]["actor_name"].endswith("<owner@team.example.com>")
    assert by_action["limit.changed"]["actor_name"].endswith("<admin@team.example.com>")
    assert by_action["limit.changed"]["summary"] == "Set the monthly spending limit to $25.50."
    assert by_action["role.changed"]["details"] == {"from": "viewer", "to": "member"}
    assert by_action["member.removed"]["target_id"] == str(team.users["member"])
    assert all(e["summary"] and e["created_at"] and e["action_label"] for e in log)
    # a key is never written into the log, only its last four characters
    everything = json.dumps(log)
    assert KEY not in everything
    assert NEW_KEY not in everything
    assert by_action["key.rotated"]["details"]["old_key_last4"] == KEY[-4:]
    assert by_action["key.rotated"]["details"]["key_last4"] == NEW_KEY[-4:]


async def test_accepting_an_invite_and_the_limit_are_recorded_for_the_new_member(
    client: httpx.AsyncClient, team: Team
) -> None:
    from tests.helpers import sign_up

    link = (
        await client.post(
            f"{team.base}/invites", json={"email": "k@example.com", "role": "member"}, headers=team.headers
        )
    ).json()["link"]
    headers = await sign_up(client, "k@example.com")
    await client.post(f"/api/v1/auth/invites/{link.rsplit('/', 1)[-1]}/accept", headers=headers)
    accepted = next(e for e in await events(client, team) if e["action"] == "invite.accepted")
    assert "k@example.com" in accepted["summary"]
    assert accepted["details"]["role"] == "member"


async def test_labelling_an_answer_is_recorded(
    client: httpx.AsyncClient, team: Team, team_session: Session, jobs: InlineJobQueue
) -> None:
    models = await judged_project(client, team_session, jobs, set_judge="scripted")
    experiment = await run_good(client, team_session, jobs, models)
    cases = (
        await client.get(f"{base(team_session)}/experiments/{experiment['id']}/cases", headers=team.headers)
    ).json()
    answer = cases[0]["outputs"][0]["test_case_run_id"]
    url = f"{base(team_session)}/experiments/{experiment['id']}/answers/{answer}/label"
    assert (await client.put(url, json={"verdict": "good"}, headers=team.h("member"))).status_code == 200
    assert (await client.delete(url, headers=team.h("member"))).status_code == 204
    labelled = [e for e in await events(client, team) if e["action"] == "answer.labelled"]
    assert len(labelled) == 2
    assert labelled[1]["details"]["verdict"] == "good"
    assert labelled[0]["details"]["verdict"] is None
    assert labelled[1]["actor_name"].endswith("<member@team.example.com>")
    assert labelled[1]["project_id"] == str(team.project_id)


async def test_moving_a_prompt_label_is_recorded(client: httpx.AsyncClient, team: Team, team_session: Session) -> None:
    first = await create_prompt(client, team_session)
    prompt_id = first["prompt_id"]
    second = (
        await client.post(
            f"{team.proj}/prompts/{prompt_id}/versions",
            json={"user_template": "Ticket v2: {{ ticket }}", "change_reason": "v2"},
            headers=team.headers,
        )
    ).json()
    label = f"{team.proj}/prompts/{prompt_id}/labels/production"
    assert (await client.put(label, json={"version_id": first["id"]}, headers=team.h("member"))).status_code == 200
    assert (await client.put(label, json={"version_id": second["id"]}, headers=team.h("member"))).status_code == 200
    assert (await client.post(f"{label}/rollback", headers=team.h("member"))).status_code == 200
    assert (await client.delete(label, headers=team.h("member"))).status_code == 204
    moved = [e for e in reversed(await events(client, team)) if e["action"] == "label.moved"]
    assert [e["details"]["reason"] for e in moved] == ["assign", "assign", "rollback", "remove"]
    assert moved[1]["details"]["from_version_id"] == first["id"]
    assert moved[1]["details"]["to_version_id"] == second["id"]
    assert moved[0]["actor_name"].endswith("<member@team.example.com>")
    assert moved[3]["summary"] == "Removed the label production from a prompt."


async def test_accepting_an_improvement_is_recorded(
    client: httpx.AsyncClient, team: Team, team_session: Session, jobs: InlineJobQueue, container: Container
) -> None:
    models = await approved_project(client, team_session, jobs)
    body = {"models": [{"model_profile_id": models["echo"], "runs": 1}]}
    experiment = (await client.post(f"{team.proj}/experiments", json=body, headers=team.headers)).json()
    await jobs.drain()
    started = await client.post(
        f"{team.proj}/improvements", json={"experiment_id": experiment["id"]}, headers=team.headers
    )
    assert started.status_code == 202, started.text
    await jobs.drain()
    result = (
        await client.get(
            f"{team.proj}/improvements/latest", params={"experiment_id": experiment["id"]}, headers=team.headers
        )
    ).json()
    chosen = next(c for c in result["candidates"] if c["holdout_experiment_id"])
    async with container.database.sessions() as db:
        row = await db.get(PromptCandidate, uuid.UUID(chosen["id"]))
        assert row is not None
        row.outcome = CandidateOutcome.BETTER
        await db.commit()
    accept = f"{team.proj}/improvements/{result['id']}/candidates/{chosen['id']}/accept"
    assert (await client.post(accept, headers=team.h("member"))).status_code == 200
    accepted = [e for e in await events(client, team) if e["action"] == "version.accepted"]
    assert len(accepted) == 1
    assert accepted[0]["actor_name"].endswith("<member@team.example.com>")


async def test_api_tokens_being_made_and_revoked_are_recorded_without_the_token(
    client: httpx.AsyncClient, team: Team
) -> None:
    made = (
        await client.post("/api/v1/auth/tokens", json={"name": "ci", "scope": "read"}, headers=team.h("admin"))
    ).json()
    await client.delete(f"/api/v1/auth/tokens/{made['id']}", headers=team.h("admin"))
    await client.delete(f"/api/v1/auth/tokens/{made['id']}", headers=team.h("admin"))  # again: nothing new to record
    log = [e for e in await events(client, team) if e["action"].startswith("token.")]
    assert [e["action"] for e in reversed(log)] == ["token.created", "token.revoked"]
    assert log[1]["details"]["scope"] == "read"
    assert made["token"] not in json.dumps(log)
    assert log[0]["actor_name"].endswith("<admin@team.example.com>")


async def test_the_log_can_be_filtered_by_action_person_project_and_dates_and_paged(
    client: httpx.AsyncClient, team: Team
) -> None:
    for limit in ("1", "2", "3"):
        await client.put(f"{team.base}/guardrails", json={"monthly_spend_limit": limit}, headers=team.headers)
    await client.patch(f"{team.base}/members/{team.users['viewer']}", json={"role": "member"}, headers=team.h("admin"))
    all_events = await events(client, team)
    assert [e["action"] for e in all_events].count("limit.changed") == 3

    assert {e["action"] for e in await events(client, team, action="role.changed")} == {"role.changed"}
    mine = await events(client, team, actor_id=str(team.users["admin"]))
    assert [e["action"] for e in mine] == ["role.changed"]
    assert await events(client, team, project_id=str(team.project_id)) == []
    now = utcnow()
    assert len(await events(client, team, since=(now - timedelta(minutes=5)).isoformat())) == 4
    assert await events(client, team, since=(now + timedelta(minutes=5)).isoformat()) == []
    assert len(await events(client, team, until=(now + timedelta(minutes=5)).isoformat())) == 4
    assert await events(client, team, until=(now - timedelta(minutes=5)).isoformat()) == []

    first = (await client.get(f"{team.base}/audit-log", params={"limit": 3}, headers=team.headers)).json()
    assert len(first["items"]) == 3
    assert first["next_cursor"]
    rest = (
        await client.get(
            f"{team.base}/audit-log", params={"limit": 3, "cursor": first["next_cursor"]}, headers=team.headers
        )
    ).json()
    assert [e["id"] for e in first["items"] + rest["items"]] == [e["id"] for e in all_events]  # newest first, no gap

    shown = (await client.get(f"{team.base}/audit-log/actions", headers=team.headers)).json()
    assert {a["action"]: a["label"] for a in shown} == {
        "limit.changed": "Spending limit changed",
        "role.changed": "Role changed",
    }


async def test_the_log_downloads_as_csv_and_json_with_the_same_filters(client: httpx.AsyncClient, team: Team) -> None:
    await client.put(f"{team.base}/guardrails", json={"monthly_spend_limit": "5"}, headers=team.headers)
    await client.patch(f"{team.base}/members/{team.users['viewer']}", json={"role": "member"}, headers=team.headers)

    as_csv = await client.get(f"{team.base}/audit-log/export", headers=team.headers)
    assert as_csv.status_code == 200, as_csv.text
    assert as_csv.headers["content-type"].startswith("text/csv")
    assert 'filename="audit-log.csv"' in as_csv.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(as_csv.text)))
    assert [r["what"] for r in rows] == ["Role changed", "Spending limit changed"]
    assert rows[1]["who"].endswith("<owner@team.example.com>")
    assert "$5.00" in rows[1]["summary"]

    as_json = await client.get(f"{team.base}/audit-log/export", params={"format": "json"}, headers=team.headers)
    assert as_json.headers["content-type"] == "application/json"
    assert 'filename="audit-log.json"' in as_json.headers["content-disposition"]
    parsed = as_json.json()
    assert [e["action"] for e in parsed] == ["role.changed", "limit.changed"]

    filtered = await client.get(
        f"{team.base}/audit-log/export", params={"format": "json", "action": "limit.changed"}, headers=team.headers
    )
    assert [e["action"] for e in filtered.json()] == ["limit.changed"]
    assert (
        await client.get(f"{team.base}/audit-log/export", params={"format": "xml"}, headers=team.headers)
    ).status_code == 422


async def test_each_workspace_sees_only_its_own_log(client: httpx.AsyncClient, team: Team) -> None:
    await client.put(f"{team.base}/guardrails", json={"monthly_spend_limit": "5"}, headers=team.headers)
    other = (await client.get("/api/v1/auth/me", headers=team.headers)).json()["organizations"]
    personal = next(o["id"] for o in other if o["is_personal"])
    mine = await client.get(f"/api/v1/organizations/{personal}/audit-log", headers=team.headers)
    assert mine.status_code == 200
    assert mine.json()["items"] == []
