"""Integration tests for Prompt Studio: immutable versions, checks and draft inspection."""

import asyncio

import httpx
import pytest

from tests.helpers import Session, add_credential

pytestmark = [pytest.mark.integration, pytest.mark.prompts]

SYSTEM = "You triage support tickets into one of: billing, shipping, technical."
USER = "Ticket:\n{{ ticket }}"


def base(session: Session) -> str:
    return f"/api/v1/projects/{session.project_id}"


async def create_prompt(client: httpx.AsyncClient, session: Session, **body: object) -> dict[str, object]:
    payload = {"name": "Triage", "system_template": SYSTEM, "user_template": USER, **body}
    response = await client.post(f"{base(session)}/prompts", json=payload, headers=session.headers)
    assert response.status_code == 201, response.text
    result: dict[str, object] = response.json()
    return result


async def test_every_save_is_a_new_immutable_version_linked_to_its_parent(
    client: httpx.AsyncClient, session: Session
) -> None:
    prompt = await create_prompt(client, session, default_params={"temperature": 0})
    first = prompt["latest_version"]
    assert isinstance(first, dict)
    assert (first["version"], first["variables"], first["shape"]) == (1, ["ticket"], "system_and_user")

    saved = await client.post(
        f"{base(session)}/prompts/{prompt['id']}/versions",
        json={"system_template": SYSTEM + " Reply in lowercase.", "user_template": USER, "change_reason": "casing"},
        headers=session.headers,
    )
    second = saved.json()
    assert (second["version"], second["parent_version_id"], second["change_reason"]) == (2, first["id"], "casing")
    original = await client.get(f"{base(session)}/prompt-versions/{first['id']}", headers=session.headers)
    assert original.json()["system_template"] == SYSTEM


async def test_concurrent_saves_get_consecutive_version_numbers(client: httpx.AsyncClient, session: Session) -> None:
    prompt = await create_prompt(client, session)
    url = f"{base(session)}/prompts/{prompt['id']}/versions"
    saves = await asyncio.gather(
        *(client.post(url, json={"user_template": f"v{n} {{{{ ticket }}}}"}, headers=session.headers) for n in range(4))
    )
    assert sorted(save.json()["version"] for save in saves) == [2, 3, 4, 5]


async def test_unknown_default_parameters_and_broken_templates_are_rejected_on_save(
    client: httpx.AsyncClient, session: Session
) -> None:
    url = f"{base(session)}/prompts"
    unknown = await client.post(
        url,
        json={"name": "x", "user_template": "{{ a }}", "default_params": {"temprature": 0}},
        headers=session.headers,
    )
    broken = await client.post(url, json={"name": "x", "user_template": "{{ a "}, headers=session.headers)
    empty = await client.post(url, json={"name": "x", "system_template": ""}, headers=session.headers)
    assert unknown.status_code == broken.status_code == empty.status_code == 422
    assert "temprature" in unknown.json()["error"]["message"]
    assert broken.json()["error"]["details"]["template"] == "user"


async def test_check_reports_missing_columns_and_models_whose_context_is_too_small(
    client: httpx.AsyncClient, session: Session
) -> None:
    await add_credential(client, session, "mock")
    models = (await client.get(f"{base(session)}/models", headers=session.headers)).json()["items"]
    echo = next(model for model in models if model["model_name"] == "echo")
    long_system = "Rules. " * 6000
    prompt = await create_prompt(client, session, system_template=long_system)
    version = prompt["latest_version"]
    assert isinstance(version, dict)

    check = await client.post(
        f"{base(session)}/prompt-versions/{version['id']}/check",
        json={"columns": ["body", "category"], "model_profile_ids": [echo["id"]]},
        headers=session.headers,
    )
    result = check.json()
    assert result["missing_inputs"] == ["ticket"]
    assert [(fit["display_name"], fit["fits"]) for fit in result["context"]] == [("echo", False)]
    assert result["ok"] is False


async def test_a_draft_can_be_inspected_and_previewed_before_it_is_saved(
    client: httpx.AsyncClient, session: Session
) -> None:
    response = await client.post(
        f"{base(session)}/prompts/inspect",
        json={"system_template": SYSTEM, "sample_inputs": {"user_message": "Where is my parcel?"}},
        headers=session.headers,
    )
    body = response.json()
    assert body["check"]["shape"] == "system_only"
    assert body["check"]["required_inputs"] == ["user_message"]
    assert body["preview"]["messages"] == [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": "Where is my parcel?"},
    ]


async def test_rendering_a_saved_version_fills_the_case_values(client: httpx.AsyncClient, session: Session) -> None:
    prompt = await create_prompt(client, session)
    version = prompt["latest_version"]
    assert isinstance(version, dict)
    url = f"{base(session)}/prompt-versions/{version['id']}/render"
    rendered = await client.post(url, json={"inputs": {"ticket": "Refund please"}}, headers=session.headers)
    assert rendered.json()["messages"][1] == {"role": "user", "content": "Ticket:\nRefund please"}
    missing = await client.post(url, json={"inputs": {}}, headers=session.headers)
    assert (missing.status_code, missing.json()["error"]["details"]["missing_inputs"]) == (422, ["ticket"])
