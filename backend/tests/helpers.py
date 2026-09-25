"""
Helpers shared by integration tests: sign-up, a signed-in project session, adding a
credential, and loading recorded provider fixtures.
"""

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests/fixtures"
PASSWORD = "correct horse battery"


@dataclass
class Session:
    headers: dict[str, str]
    user_id: uuid.UUID
    project_id: uuid.UUID


async def sign_up(client: httpx.AsyncClient, email: str, password: str = PASSWORD) -> dict[str, str]:
    response = await client.post("/api/v1/auth/signup", json={"email": email, "password": password, "name": "Ada"})
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def add_credential(client: httpx.AsyncClient, session: Session, provider: str, **extra: Any) -> dict[str, Any]:
    response = await client.post(
        f"/api/v1/projects/{session.project_id}/credentials",
        json={"provider": provider, **extra},
        headers=session.headers,
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def provider_fixture(provider: str, name: str) -> Any:
    return json.loads((FIXTURES / "providers" / provider / name).read_text())
