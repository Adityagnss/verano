"""Integration tests for deleting a prompt (used by `verano push --prune`): confirmation flag, refusal when used."""

import httpx
import pytest

from app.core.jobs import InlineJobQueue
from tests.helpers import Session, approved_project, base

pytestmark = [pytest.mark.integration, pytest.mark.prompts]


async def test_deleting_a_prompt_needs_confirmation_and_removes_versions_and_labels(
    client: httpx.AsyncClient, session: Session
) -> None:
    created = (
        await client.post(
            f"{base(session)}/prompts", json={"name": "Triage", "user_template": "Hi {{ x }}"}, headers=session.headers
        )
    ).json()
    version = created["latest_version"]["id"]
    url = f"{base(session)}/prompts/{created['id']}"
    labelled = await client.put(f"{url}/labels/production", json={"version_id": version}, headers=session.headers)
    assert labelled.status_code == 200

    unconfirmed = await client.delete(url, headers=session.headers)
    assert unconfirmed.status_code == 422
    assert "confirm=true" in unconfirmed.text
    assert (await client.get(url, headers=session.headers)).status_code == 200

    assert (await client.delete(url, params={"confirm": "true"}, headers=session.headers)).status_code == 204
    assert (await client.get(url, headers=session.headers)).status_code == 404
    assert (await client.get(f"{base(session)}/prompt-versions/{version}", headers=session.headers)).status_code == 404
    assert (await client.delete(url, params={"confirm": "true"}, headers=session.headers)).status_code == 404
    gone = await client.get(f"{base(session)}/prompt-by-name/Triage", headers=session.headers)
    assert gone.status_code == 404


async def test_a_read_token_cannot_delete_and_the_deletion_is_audited(
    client: httpx.AsyncClient, session: Session
) -> None:
    created = (
        await client.post(f"{base(session)}/prompts", json={"name": "A", "user_template": "x"}, headers=session.headers)
    ).json()
    url = f"{base(session)}/prompts/{created['id']}"
    token = (
        await client.post("/api/v1/auth/tokens", json={"name": "r", "scope": "read"}, headers=session.headers)
    ).json()
    refused = await client.delete(
        url, params={"confirm": "true"}, headers={"Authorization": f"Bearer {token['token']}"}
    )
    assert refused.status_code == 403
    assert (await client.delete(url, params={"confirm": "true"}, headers=session.headers)).status_code == 204
    me = (await client.get("/api/v1/auth/me", headers=session.headers)).json()
    organization = me["organizations"][0]["id"]
    audit = await client.get(f"/api/v1/organizations/{organization}/audit-log", headers=session.headers)
    assert audit.status_code == 200
    assert "prompt.deleted" in audit.text


async def test_a_prompt_with_experiment_results_cannot_be_deleted(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue
) -> None:
    models = await approved_project(client, session, jobs)
    body = {"models": [{"model_profile_id": models["good"], "runs": 1}]}
    assert (await client.post(f"{base(session)}/experiments", json=body, headers=session.headers)).status_code == 201
    await jobs.drain()
    prompt = (await client.get(f"{base(session)}/prompts", headers=session.headers)).json()["items"][0]
    url = f"{base(session)}/prompts/{prompt['id']}"
    refused = await client.delete(url, params={"confirm": "true"}, headers=session.headers)
    assert refused.status_code == 409
    assert "experiment" in refused.text
    assert (await client.get(url, headers=session.headers)).status_code == 200
