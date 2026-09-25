"""
Integration tests for credentials and model discovery, replaying each provider's recorded
responses with respx: discovery parsing, chat filtering, profiles, bad keys, key secrecy.
"""

import json
import logging
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import httpx
import pytest
import respx
from sqlalchemy import text

from app.core.container import Container
from tests.helpers import Session, add_credential, provider_fixture

pytestmark = [pytest.mark.integration, pytest.mark.registry]

KEY = "sk-test-0123456789abcdefghij-1234"
OLLAMA = "http://ollama.test:11434"


def fixture_response(provider: str, name: str, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=provider_fixture(provider, name))


def ollama_show(request: httpx.Request) -> httpx.Response:
    model = json.loads(request.content)["model"].replace(":", "_")
    return fixture_response("ollama", f"show_{model}.json")


ROUTES: dict[str, Callable[[respx.MockRouter], object]] = {
    "openai": lambda m: m.get("https://api.openai.com/v1/models").mock(fixture_response("openai", "models.json")),
    "anthropic": lambda m: (
        m.get("https://api.anthropic.com/v1/models", params={"after_id": "claude-3-5-haiku-20241022"}).mock(
            fixture_response("anthropic", "models_page2.json")
        ),
        m.get("https://api.anthropic.com/v1/models").mock(fixture_response("anthropic", "models.json")),
    ),
    "gemini": lambda m: (
        m.get("https://generativelanguage.googleapis.com/v1beta/models", params={"pageToken": "page-2"}).mock(
            fixture_response("gemini", "models_page2.json")
        ),
        m.get("https://generativelanguage.googleapis.com/v1beta/models").mock(
            fixture_response("gemini", "models.json")
        ),
    ),
    "groq": lambda m: m.get("https://api.groq.com/openai/v1/models").mock(fixture_response("groq", "models.json")),
    "mistral": lambda m: m.get("https://api.mistral.ai/v1/models").mock(fixture_response("mistral", "models.json")),
    "together": lambda m: m.get("https://api.together.xyz/v1/models").mock(fixture_response("together", "models.json")),
    "openrouter": lambda m: m.get("https://openrouter.ai/api/v1/models").mock(
        fixture_response("openrouter", "models.json")
    ),
    "ollama": lambda m: (
        m.get(f"{OLLAMA}/api/tags").mock(fixture_response("ollama", "tags.json")),
        m.post(f"{OLLAMA}/api/show").mock(side_effect=ollama_show),
    ),
}

AUTH_URLS = {
    "openai": ("https://api.openai.com/v1/models", 401),
    "anthropic": ("https://api.anthropic.com/v1/models", 401),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/models", 400),
    "groq": ("https://api.groq.com/openai/v1/models", 401),
    "mistral": ("https://api.mistral.ai/v1/models", 401),
    "together": ("https://api.together.xyz/v1/models", 401),
    "openrouter": ("https://openrouter.ai/api/v1/models", 401),
}


@dataclass
class Expected:
    chat_models: set[str]
    profiles: dict[str, dict[str, Any]] = field(default_factory=dict)


EXPECTED: dict[str, Expected] = {
    "openai": Expected(
        {"gpt-4o-mini", "gpt-4o", "ft:gpt-4o-mini-2024-07-18:acme::A1b2C3d4"},
        {
            "gpt-4o-mini": {"price_source": "litellm", "price_known": True, "supports_json_mode": True},
            "ft:gpt-4o-mini-2024-07-18:acme::A1b2C3d4": {"price_known": False, "input_price_per_mtok": None},
        },
    ),
    "anthropic": Expected(
        {"claude-sonnet-4-5-20250929", "claude-3-5-haiku-20241022", "claude-3-haiku-20240307"},
        {"claude-3-5-haiku-20241022": {"display_name": "Claude Haiku 3.5"}},
    ),
    "gemini": Expected(
        {"gemini-2.0-flash", "gemini-1.5-flash"},
        {
            "gemini-2.0-flash": {
                "context_window": 1048576,
                "max_output_tokens": 8192,
                "display_name": "Gemini 2.0 Flash",
            }
        },
    ),
    "groq": Expected({"llama-3.1-8b-instant"}, {"llama-3.1-8b-instant": {"context_window": 131072}}),
    "mistral": Expected({"mistral-small-latest"}, {"mistral-small-latest": {"context_window": 32768}}),
    "together": Expected(
        {"meta-llama/Llama-3.3-70B-Instruct-Turbo"},
        {"meta-llama/Llama-3.3-70B-Instruct-Turbo": {"input_price_per_mtok": "0.88", "price_source": "provider"}},
    ),
    "openrouter": Expected(
        {"openai/gpt-4o-mini"},
        {
            "openai/gpt-4o-mini": {
                "input_price_per_mtok": "0.15",
                "output_price_per_mtok": "0.6",
                "price_source": "provider",
                "max_output_tokens": 16384,
                "supports_json_mode": True,
            }
        },
    ),
    "ollama": Expected(
        {"qwen2.5:3b"},
        {"qwen2.5:3b": {"context_window": 32768, "input_price_per_mtok": "0", "price_source": "free"}},
    ),
}


@pytest.fixture
def providers() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as mock:
        yield mock


def credential_body(provider: str) -> dict[str, Any]:
    return {} if provider == "ollama" else {"api_key": KEY}


async def list_models(client: httpx.AsyncClient, session: Session) -> dict[str, dict[str, Any]]:
    response = await client.get(f"/api/v1/projects/{session.project_id}/models", headers=session.headers)
    return {m["model_name"]: m for m in response.json()["items"]}


@pytest.mark.parametrize("provider", sorted(EXPECTED))
async def test_discovery_parses_each_providers_recorded_listing_into_chat_model_profiles(
    client: httpx.AsyncClient, session: Session, providers: respx.MockRouter, provider: str
) -> None:
    ROUTES[provider](providers)
    credential = await add_credential(client, session, provider, **credential_body(provider))
    expected = EXPECTED[provider]
    assert credential["model_count"] == len(expected.chat_models)
    models = await list_models(client, session)
    assert set(models) == expected.chat_models
    for name, attributes in expected.profiles.items():
        assert {key: models[name][key] for key in attributes} == attributes


@pytest.mark.parametrize("provider", sorted(AUTH_URLS))
async def test_a_rejected_key_fails_immediately_with_a_clear_message_and_nothing_is_stored(
    client: httpx.AsyncClient, session: Session, providers: respx.MockRouter, provider: str
) -> None:
    url, status = AUTH_URLS[provider]
    providers.get(url__startswith=url).mock(fixture_response(provider, "auth_error.json", status))
    response = await client.post(
        f"/api/v1/projects/{session.project_id}/credentials",
        json={"provider": provider, "api_key": "sk-wrong-key-0000"},
        headers=session.headers,
    )
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "provider_auth_error"
    assert error["message"].startswith("This key was rejected by ")
    assert "Check that it's active" in error["message"]
    listed = await client.get(f"/api/v1/projects/{session.project_id}/credentials", headers=session.headers)
    assert listed.json() == []


async def test_an_unreachable_ollama_says_which_address_was_tried(
    client: httpx.AsyncClient, session: Session, providers: respx.MockRouter
) -> None:
    providers.get(f"{OLLAMA}/api/tags").mock(side_effect=httpx.ConnectError("refused"))
    response = await client.post(
        f"/api/v1/projects/{session.project_id}/credentials", json={"provider": "ollama"}, headers=session.headers
    )
    assert response.status_code == 503
    assert OLLAMA in response.json()["error"]["message"]


async def test_a_key_is_encrypted_at_rest_and_never_returned_or_logged(
    client: httpx.AsyncClient,
    session: Session,
    providers: respx.MockRouter,
    container: Container,
    caplog: pytest.LogCaptureFixture,
) -> None:
    ROUTES["openai"](providers)
    caplog.set_level(logging.DEBUG)
    created = await client.post(
        f"/api/v1/projects/{session.project_id}/credentials",
        json={"provider": "openai", "api_key": KEY},
        headers=session.headers,
    )
    listed = await client.get(f"/api/v1/projects/{session.project_id}/credentials", headers=session.headers)
    models = await client.get(f"/api/v1/projects/{session.project_id}/models", headers=session.headers)

    for response in (created, listed, models):
        assert KEY not in response.text
    assert created.json()["key_last4"] == "1234"
    assert KEY not in caplog.text
    assert providers.calls.last.request.headers["authorization"] == f"Bearer {KEY}"

    async with container.database.engine.connect() as connection:
        stored: bytes = (await connection.execute(text("SELECT encrypted_key FROM provider_credentials"))).scalar_one()
    assert KEY.encode() not in stored
    assert container.secret_box.decrypt(stored) == KEY


async def test_model_selection_survives_rediscovery(
    client: httpx.AsyncClient, session: Session, providers: respx.MockRouter
) -> None:
    ROUTES["openai"](providers)
    credential = await add_credential(client, session, "openai", api_key=KEY)
    chosen = (await list_models(client, session))["gpt-4o-mini"]["id"]
    base = f"/api/v1/projects/{session.project_id}"
    await client.put(f"{base}/models/selection", json={"selected": [chosen]}, headers=session.headers)
    await client.post(f"{base}/credentials/{credential['id']}/discover", headers=session.headers)

    selected = await client.get(f"{base}/models", params={"selected": True}, headers=session.headers)
    assert [m["model_name"] for m in selected.json()["items"]] == ["gpt-4o-mini"]


async def test_mock_models_carry_their_fake_prices_for_real_cost_arithmetic(
    client: httpx.AsyncClient, session: Session
) -> None:
    await add_credential(client, session, "mock")
    echo = (await list_models(client, session))["echo"]
    assert (Decimal(echo["input_price_per_mtok"]), Decimal(echo["output_price_per_mtok"])) == (
        Decimal("0.5"),
        Decimal("1.5"),
    )
