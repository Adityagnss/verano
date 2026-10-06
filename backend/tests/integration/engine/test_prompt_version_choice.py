"""An experiment can test any saved prompt version, as long as it takes the inputs the test cases give."""

import httpx
import pytest

from app.core.jobs import InlineJobQueue
from tests.helpers import Session, approved_project

pytestmark = [pytest.mark.integration]


async def test_an_older_version_can_be_run_and_one_with_other_inputs_is_refused(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue
) -> None:
    base = f"/api/v1/projects/{session.project_id}"
    models = await approved_project(client, session, jobs)
    prompt = (await client.get(f"{base}/prompts", headers=session.headers)).json()["items"][0]
    first = prompt["latest_version"]
    second = await client.post(
        f"{base}/prompts/{prompt['id']}/versions",
        json={"system_template": "Classify the ticket. Reply with exactly one word."},
        headers=session.headers,
    )
    assert second.status_code == 201, second.text
    run = {"models": [{"model_profile_id": models["echo"], "runs": 1}], "prompt_version_id": first["id"]}
    started = await client.post(f"{base}/experiments", json=run, headers=session.headers)
    assert started.status_code in (200, 201, 202), started.text
    assert started.json()["prompt_version_id"] == first["id"]

    other = await client.post(
        f"{base}/prompts/{prompt['id']}/versions",
        json={"system_template": "Classify.", "user_template": "Ticket: {{ ticket }}"},
        headers=session.headers,
    )
    refused = await client.post(
        f"{base}/experiments", json={**run, "prompt_version_id": other.json()["id"]}, headers=session.headers
    )
    assert refused.status_code == 422, refused.text
    assert "needs the inputs ticket" in refused.json()["error"]["message"]


async def test_two_prompt_versions_are_compared_per_model_on_the_same_cases(
    client: httpx.AsyncClient, session: Session, jobs: InlineJobQueue
) -> None:
    base = f"/api/v1/projects/{session.project_id}"
    models = await approved_project(client, session, jobs)
    prompt = (await client.get(f"{base}/prompts", headers=session.headers)).json()["items"][0]
    first = prompt["latest_version"]
    second = (
        await client.post(
            f"{base}/prompts/{prompt['id']}/versions",
            json={"system_template": "Classify the ticket. Reply with exactly one word."},
            headers=session.headers,
        )
    ).json()
    run = {"models": [{"model_profile_id": models["echo"], "runs": 1}]}
    old = (
        await client.post(
            f"{base}/experiments", json={**run, "prompt_version_id": first["id"]}, headers=session.headers
        )
    ).json()
    new = (
        await client.post(
            f"{base}/experiments", json={**run, "prompt_version_id": second["id"]}, headers=session.headers
        )
    ).json()
    await jobs.drain()

    compared = await client.get(
        f"{base}/experiments/{new['id']}/compare", params={"against": old["id"]}, headers=session.headers
    )
    assert compared.status_code == 200, compared.text
    body = compared.json()
    assert (body["prompt_version"], body["against_prompt_version"], body["same_test_cases"]) == (2, 1, True)
    (model,) = body["models"]
    assert model["comparison"]["cases"] == 3
    assert model["comparison"]["label"] == "too few cases"
    assert len(model["fixed"]) + len(model["broken"]) <= 3
    same = await client.get(
        f"{base}/experiments/{new['id']}/compare", params={"against": new["id"]}, headers=session.headers
    )
    assert same.status_code == 409
