"""
Fixtures for the teams tests: a shared workspace with one person in each role, each with their own sign-in,
and a project in it. Shared workspaces have no create route yet, so they are inserted directly.
"""

import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field

import httpx
import pytest
import respx

from app.core.container import Container
from app.modules.auth.models import Membership, Organization
from app.modules.auth.schemas import MembershipRole
from tests.helpers import Session, sign_up

OPENAI_MODELS = "https://api.openai.com/v1/models"


@dataclass
class Team:
    organization_id: uuid.UUID
    project_id: uuid.UUID
    headers: dict[str, str]  # the owner
    users: dict[str, uuid.UUID] = field(default_factory=dict)
    emails: dict[str, str] = field(default_factory=dict)
    sessions: dict[str, dict[str, str]] = field(default_factory=dict)

    def h(self, role: str) -> dict[str, str]:
        return self.sessions[role]

    @property
    def base(self) -> str:
        return f"/api/v1/organizations/{self.organization_id}"

    @property
    def proj(self) -> str:
        return f"/api/v1/projects/{self.project_id}"


async def new_project(client: httpx.AsyncClient, team: Team, name: str) -> uuid.UUID:
    response = await client.post(
        "/api/v1/projects", json={"name": name, "organization_id": str(team.organization_id)}, headers=team.headers
    )
    assert response.status_code == 201, response.text
    return uuid.UUID(response.json()["id"])


@pytest.fixture
async def team(client: httpx.AsyncClient, container: Container) -> Team:
    people: dict[str, tuple[dict[str, str], uuid.UUID, str]] = {}
    for role in ("owner", "admin", "member", "viewer"):
        email = f"{role}@team.example.com"
        headers = await sign_up(client, email)
        me = (await client.get("/api/v1/auth/me", headers=headers)).json()
        people[role] = (headers, uuid.UUID(me["user"]["id"]), email)
    async with container.database.sessions() as db:
        org = Organization(name="Acme", is_personal=False)
        db.add(org)
        await db.flush()
        for role, (_, user_id, _) in people.items():
            db.add(Membership(organization_id=org.id, user_id=user_id, role=MembershipRole(role)))
        await db.commit()
        org_id = org.id
    built = Team(organization_id=org_id, project_id=uuid.uuid4(), headers=people["owner"][0])
    for role, (headers, user_id, email) in people.items():
        built.sessions[role] = headers
        built.users[role] = user_id
        built.emails[role] = email
    built.project_id = await new_project(client, built, "Support triage")
    return built


@pytest.fixture
def team_session(team: Team) -> Session:
    return Session(headers=team.headers, user_id=team.users["owner"], project_id=team.project_id)


class ProviderMock:
    """OpenAI's model list that accepts only the keys in `valid`."""

    def __init__(self, router: respx.MockRouter) -> None:
        self.valid: set[str] = set()
        self.seen: list[str] = []
        router.get(OPENAI_MODELS).mock(side_effect=self._answer)

    def _answer(self, request: httpx.Request) -> httpx.Response:
        key = request.headers.get("authorization", "").removeprefix("Bearer ")
        self.seen.append(key)
        if key in self.valid:
            return httpx.Response(200, json={"object": "list", "data": [{"id": "gpt-4o-mini", "object": "model"}]})
        return httpx.Response(401, json={"error": {"message": "Incorrect API key provided", "type": "invalid"}})


@pytest.fixture
def provider() -> Iterator[ProviderMock]:
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        yield ProviderMock(router)
