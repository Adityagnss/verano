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
    client: httpx.AsyncClient, session: Session, name: str, content: bytes, purpose: str = "golden"
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
    client: httpx.AsyncClient, session: Session, file_id: str, mapping: dict[str, Any]
) -> httpx.Response:
    return await client.put(
        f"/api/v1/projects/{session.project_id}/input-files/{file_id}/mapping",
        json={"mapping": mapping},
        headers=session.headers,
    )


async def import_file(client: httpx.AsyncClient, session: Session, file_id: str) -> httpx.Response:
    return await client.post(
        f"/api/v1/projects/{session.project_id}/input-files/{file_id}/import", headers=session.headers
    )


async def add_input_files(client: httpx.AsyncClient, session: Session, jobs: Any, texts: list[str]) -> list[str]:
    """Uploads one input file per text (each becomes one test case); returns the file ids."""
    ids = []
    for number, text in enumerate(texts, start=1):
        response = await upload(client, session, f"case{number}.txt", text.encode(), purpose="input")
        assert response.status_code == 201, response.text
        await jobs.drain()
        ids.append(response.json()["id"])
    return ids


async def add_golden(
    client: httpx.AsyncClient, session: Session, jobs: Any, name: str, content: bytes, mapping: dict[str, Any]
) -> dict[str, Any]:
    """Uploads a golden set, confirms its mapping and imports it onto the input files."""
    response = await upload(client, session, name, content)
    assert response.status_code == 201, response.text
    file_id = response.json()["id"]
    await jobs.drain()
    assert (await map_file(client, session, file_id, mapping)).status_code == 200
    await jobs.drain()
    assert (await import_file(client, session, file_id)).status_code == 200
    await jobs.drain()
    return await get_file(client, session, file_id)


GOLDEN_TICKETS = (
    "ticket,expected\nMy card was charged twice,billing\nWhere is my parcel?,shipping\n"
    "The app crashes on start,technical\n"
)


async def approved_project(client: httpx.AsyncClient, session: Session, jobs: Any) -> dict[str, str]:
    """A project with mock models, a system-only prompt, and the 3 golden tickets approved
    (golden only, so no generation). Returns mock model profile ids by model name."""
    base = f"/api/v1/projects/{session.project_id}"
    credential = await add_credential(client, session, "mock")
    version = await create_prompt(client, session, system_template="Classify the support ticket. Reply with one word.")
    await add_input_files(
        client, session, jobs, ["My card was charged twice", "Where is my parcel?", "The app crashes on start"]
    )
    await add_golden(client, session, jobs, "golden.csv", GOLDEN_TICKETS.encode(), {"expected_output": "expected"})
    spec_body = {"prompt_version_id": version["id"], "credential_id": credential["id"], "model": "scripted"}
    spec = (await client.post(f"{base}/task-specs", json=spec_body, headers=session.headers)).json()
    await client.put(f"{base}/task-specs/{spec['id']}", json={"spec": spec["spec"]}, headers=session.headers)
    generation = {"task_spec_id": spec["id"], "golden_only": True}
    started = await client.post(f"{base}/generations", json=generation, headers=session.headers)
    await jobs.drain()
    approved = await client.post(f"{base}/dataset-versions/{started.json()['id']}/approve", headers=session.headers)
    assert approved.status_code == 200, approved.text
    models = await client.get(f"{base}/models", params={"limit": 200}, headers=session.headers)
    return {model["model_name"]: model["id"] for model in models.json()["items"]}
