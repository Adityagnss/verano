"""
Helpers shared by integration tests: sign-up, a signed-in project session, adding a
credential, loading recorded provider fixtures, the pinned image of a Compose service
(docker-compose.yml is the one place image versions are written down), and the file
ingestion flow as a user drives it: create a prompt, upload, map, import.
"""

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import yaml

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests/fixtures"
COMPOSE_FILE = ROOT.parent / "docker-compose.yml"
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


def compose_image(service: str) -> str:
    services = yaml.safe_load(COMPOSE_FILE.read_text())["services"]
    image: str = services[service]["image"]
    return image


async def create_prompt(client: httpx.AsyncClient, session: Session, **templates: str) -> dict[str, Any]:
    body = {"name": "Triage", **(templates or {"user_template": "Ticket: {{ ticket }}"})}
    response = await client.post(f"/api/v1/projects/{session.project_id}/prompts", json=body, headers=session.headers)
    assert response.status_code == 201, response.text
    version: dict[str, Any] = response.json()["latest_version"]
    return version


async def upload(
    client: httpx.AsyncClient, session: Session, name: str, content: bytes, purpose: str = "rows"
) -> httpx.Response:
    return await client.post(
        f"/api/v1/projects/{session.project_id}/input-files",
        files={"file": (name, content, "application/octet-stream")},
        data={"purpose": purpose},
        headers=session.headers,
    )


async def get_file(client: httpx.AsyncClient, session: Session, file_id: str) -> dict[str, Any]:
    response = await client.get(f"/api/v1/projects/{session.project_id}/input-files/{file_id}", headers=session.headers)
    body: dict[str, Any] = response.json()
    return body


async def map_file(
    client: httpx.AsyncClient, session: Session, file_id: str, version_id: str, mapping: dict[str, Any]
) -> httpx.Response:
    return await client.put(
        f"/api/v1/projects/{session.project_id}/input-files/{file_id}/mapping",
        json={"prompt_version_id": version_id, "mapping": mapping},
        headers=session.headers,
    )


async def import_file(client: httpx.AsyncClient, session: Session, file_id: str) -> httpx.Response:
    return await client.post(
        f"/api/v1/projects/{session.project_id}/input-files/{file_id}/import", headers=session.headers
    )
