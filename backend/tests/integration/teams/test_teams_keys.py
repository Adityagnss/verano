"""
S8.12: the workspace key store. One key used in three projects, rotated everywhere at once after the provider
accepts the new one; a project's own key can be moved to the store; a key in use cannot be deleted.
"""

import uuid

import httpx
import pytest
from sqlalchemy import select

from app.core.container import Container
from app.modules.registry.models import ProviderCredential
from tests.integration.teams.conftest import ProviderMock, Team, new_project

pytestmark = [pytest.mark.integration, pytest.mark.registry]

OLD = "sk-old-0123456789abcdefghij-1111"
NEW = "sk-new-0123456789abcdefghij-2222"


async def add_key(client: httpx.AsyncClient, team: Team, api_key: str = OLD, by: str = "admin") -> httpx.Response:
    return await client.post(
        f"{team.base}/keys", json={"provider": "openai", "api_key": api_key, "label": "Shared"}, headers=team.h(by)
    )


async def stored_keys(container: Container, project_id: uuid.UUID) -> list[str]:
    async with container.database.sessions() as db:
        rows = (await db.scalars(select(ProviderCredential).where(ProviderCredential.project_id == project_id))).all()
    return [container.secret_box.decrypt(r.encrypted_key) for r in rows if r.encrypted_key]


async def test_a_key_is_checked_stored_encrypted_and_never_shown(
    client: httpx.AsyncClient, team: Team, provider: ProviderMock
) -> None:
    refused = await add_key(client, team)  # the provider says no
    assert refused.status_code in {401, 422, 400}
    assert (await client.get(f"{team.base}/keys", headers=team.headers)).json() == []

    provider.valid.add(OLD)
    created = await add_key(client, team)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["key_last4"] == OLD[-4:]
    assert body["used_in"] == []
    assert OLD not in created.text
    assert OLD not in (await client.get(f"{team.base}/keys", headers=team.headers)).text
    assert (await add_key(client, team, "", by="owner")).status_code == 422
    assert (await add_key(client, team, by="member")).status_code == 403  # members may look, not add
    assert (await client.get(f"{team.base}/keys", headers=team.h("member"))).status_code == 200
    assert (await client.get(f"{team.base}/keys", headers=team.h("viewer"))).status_code == 403


async def test_one_key_serves_three_projects_and_rotating_it_changes_all_three(
    client: httpx.AsyncClient, team: Team, provider: ProviderMock, container: Container
) -> None:
    provider.valid.add(OLD)
    key = (await add_key(client, team)).json()
    projects = [team.project_id, await new_project(client, team, "Two"), await new_project(client, team, "Three")]
    for project_id in projects:
        attached = await client.post(
            f"{team.base}/keys/{key['id']}/projects", json={"project_id": str(project_id)}, headers=team.h("admin")
        )
        assert attached.status_code == 201, attached.text
    again = await client.post(
        f"{team.base}/keys/{key['id']}/projects", json={"project_id": str(projects[0])}, headers=team.headers
    )
    assert again.status_code == 409
    listed = (await client.get(f"{team.base}/keys", headers=team.headers)).json()[0]
    assert {p["project_id"] for p in listed["used_in"]} == {str(p) for p in projects}
    for project_id in projects:
        assert await stored_keys(container, project_id) == [OLD]

    # a rejected new key changes nothing
    refused = await client.post(f"{team.base}/keys/{key['id']}/rotate", json={"api_key": NEW}, headers=team.headers)
    assert refused.status_code >= 400
    for project_id in projects:
        assert await stored_keys(container, project_id) == [OLD]

    provider.valid.discard(OLD)  # the old key is revoked at the provider as part of the rotation
    provider.valid.add(NEW)
    provider.seen.clear()
    rotated = await client.post(f"{team.base}/keys/{key['id']}/rotate", json={"api_key": NEW}, headers=team.headers)
    assert rotated.status_code == 200, rotated.text
    assert rotated.json()["key_last4"] == NEW[-4:]
    assert rotated.json()["rotated_at"] is not None
    assert provider.seen[0] == NEW  # checked before it replaced anything
    for project_id in projects:
        assert await stored_keys(container, project_id) == [NEW]  # the old key is stored nowhere

    # and each project really calls the provider with the new key from now on
    provider.seen.clear()
    credentials = (await client.get(f"/api/v1/projects/{projects[2]}/credentials", headers=team.headers)).json()
    refreshed = await client.post(
        f"/api/v1/projects/{projects[2]}/credentials/{credentials[0]['id']}/discover", headers=team.headers
    )
    assert refreshed.status_code == 200, refreshed.text
    assert set(provider.seen) == {NEW}


async def test_a_key_that_projects_use_cannot_be_deleted_until_they_stop_using_it(
    client: httpx.AsyncClient, team: Team, provider: ProviderMock, container: Container
) -> None:
    provider.valid.add(OLD)
    key = (await add_key(client, team)).json()
    attach = f"{team.base}/keys/{key['id']}/projects"
    await client.post(attach, json={"project_id": str(team.project_id)}, headers=team.headers)
    blocked = await client.delete(f"{team.base}/keys/{key['id']}", headers=team.headers)
    assert blocked.status_code == 409
    assert "Support triage" in blocked.json()["error"]["message"]

    detached = await client.delete(f"{attach}/{team.project_id}", headers=team.headers)
    assert detached.status_code == 200
    assert detached.json()["used_in"] == []
    assert await stored_keys(container, team.project_id) == [OLD]  # the project keeps its own copy
    assert (await client.delete(f"{attach}/{team.project_id}", headers=team.headers)).status_code == 404
    assert (await client.delete(f"{team.base}/keys/{key['id']}", headers=team.headers)).status_code == 204
    assert (await client.delete(f"{team.base}/keys/{key['id']}", headers=team.headers)).status_code == 404


async def test_the_label_and_limits_of_a_key_follow_into_the_projects_that_use_it(
    client: httpx.AsyncClient, team: Team, provider: ProviderMock
) -> None:
    provider.valid.add(OLD)
    key = (await add_key(client, team)).json()
    await client.post(
        f"{team.base}/keys/{key['id']}/projects", json={"project_id": str(team.project_id)}, headers=team.headers
    )
    changed = await client.patch(
        f"{team.base}/keys/{key['id']}", json={"label": "Renamed", "rpm_limit": 30}, headers=team.headers
    )
    assert changed.status_code == 200
    assert changed.json()["label"] == "Renamed"
    credentials = (await client.get(f"{team.proj}/credentials", headers=team.headers)).json()
    assert [(c["label"], c["rpm_limit"]) for c in credentials] == [("Renamed", 30)]


async def test_a_project_key_moves_to_the_workspace_and_the_same_key_elsewhere_follows_it(
    client: httpx.AsyncClient, team: Team, provider: ProviderMock, container: Container
) -> None:
    provider.valid.update({OLD, NEW})
    other = await new_project(client, team, "Other")
    mine = {}
    for project_id in (team.project_id, other):
        response = await client.post(
            f"/api/v1/projects/{project_id}/credentials",
            json={"provider": "openai", "api_key": OLD},
            headers=team.headers,
        )
        assert response.status_code == 201, response.text
        mine[project_id] = response.json()["id"]
    different = await new_project(client, team, "Different")
    await client.post(
        f"/api/v1/projects/{different}/credentials", json={"provider": "openai", "api_key": NEW}, headers=team.headers
    )

    moved = await client.post(
        f"{team.base}/keys/from-credential",
        json={"project_id": str(team.project_id), "credential_id": mine[team.project_id]},
        headers=team.headers,
    )
    assert moved.status_code == 201, moved.text
    assert {p["project_id"] for p in moved.json()["used_in"]} == {str(team.project_id), str(other)}  # not "Different"
    for project_id in (team.project_id, other, different):
        assert len(await stored_keys(container, project_id)) == 1  # nothing stopped working, nothing duplicated

    again = await client.post(
        f"{team.base}/keys/from-credential",
        json={"project_id": str(team.project_id), "credential_id": mine[team.project_id]},
        headers=team.headers,
    )
    assert again.status_code == 409
    provider.valid.discard(OLD)
    provider.valid.add("sk-rot-0123456789abcdefghij-3333")
    rotated = await client.post(
        f"{team.base}/keys/{moved.json()['id']}/rotate",
        json={"api_key": "sk-rot-0123456789abcdefghij-3333"},
        headers=team.headers,
    )
    assert rotated.status_code == 200
    assert await stored_keys(container, other) == ["sk-rot-0123456789abcdefghij-3333"]
    assert await stored_keys(container, different) == [NEW]  # a different key is left alone


async def test_only_projects_of_this_workspace_and_real_keys_can_be_used(
    client: httpx.AsyncClient, team: Team, provider: ProviderMock
) -> None:
    from tests.helpers import sign_up

    provider.valid.add(OLD)
    key = (await add_key(client, team)).json()
    outsider = await sign_up(client, "outsider@example.com")
    foreign = (await client.post("/api/v1/projects", json={"name": "Not yours"}, headers=outsider)).json()["id"]
    refused = await client.post(
        f"{team.base}/keys/{key['id']}/projects", json={"project_id": foreign}, headers=team.headers
    )
    assert refused.status_code == 404
    unknown = await client.post(
        f"{team.base}/keys/{uuid.uuid4()}/projects", json={"project_id": str(team.project_id)}, headers=team.headers
    )
    assert unknown.status_code == 404
    mock_key = await client.post(f"{team.proj}/credentials", json={"provider": "mock"}, headers=team.headers)
    moved = await client.post(
        f"{team.base}/keys/from-credential",
        json={"project_id": str(team.project_id), "credential_id": mock_key.json()["id"]},
        headers=team.headers,
    )
    assert moved.status_code == 422  # a provider that needs no key has nothing to move


async def test_keys_added_before_the_workspace_store_existed_keep_working(
    client: httpx.AsyncClient, team: Team, provider: ProviderMock
) -> None:
    """A project credential made the old way (no workspace key behind it) is untouched by the new tables."""
    provider.valid.add(OLD)
    made = await client.post(
        f"{team.proj}/credentials", json={"provider": "openai", "api_key": OLD}, headers=team.headers
    )
    assert made.status_code == 201
    refreshed = await client.post(f"{team.proj}/credentials/{made.json()['id']}/discover", headers=team.headers)
    assert refreshed.status_code == 200
    assert provider.seen[-1] == OLD
    assert (await client.get(f"{team.base}/keys", headers=team.headers)).json() == []
