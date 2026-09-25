"""Integration tests for project creation, workspace isolation and cursor pagination."""

import httpx
import pytest

from tests.helpers import sign_up

pytestmark = [pytest.mark.integration, pytest.mark.projects]


async def test_projects_are_visible_only_inside_their_workspace(client: httpx.AsyncClient) -> None:
    owner = await sign_up(client, "owner@example.com")
    stranger = await sign_up(client, "stranger@example.com")
    project = (await client.post("/api/v1/projects", json={"name": "Triage"}, headers=owner)).json()

    assert (await client.get(f"/api/v1/projects/{project['id']}", headers=owner)).status_code == 200
    hidden = await client.get(f"/api/v1/projects/{project['id']}", headers=stranger)
    assert hidden.status_code == 404
    assert (await client.get("/api/v1/projects", headers=stranger)).json()["items"] == []


async def test_project_list_pages_newest_first_with_an_opaque_cursor(client: httpx.AsyncClient) -> None:
    headers = await sign_up(client, "pager@example.com")
    names = ["one", "two", "three"]
    for name in names:
        await client.post("/api/v1/projects", json={"name": name}, headers=headers)

    first = (await client.get("/api/v1/projects", params={"limit": 2}, headers=headers)).json()
    assert [p["name"] for p in first["items"]] == ["three", "two"]
    second = (
        await client.get("/api/v1/projects", params={"limit": 2, "cursor": first["next_cursor"]}, headers=headers)
    ).json()
    assert ([p["name"] for p in second["items"]], second["next_cursor"]) == (["one"], None)
