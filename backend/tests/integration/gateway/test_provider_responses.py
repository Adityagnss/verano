"""
Recorded provider chat responses replayed through the real LiteLLM path.

Proves that each provider's documented success, 429, 400, 401 and content-policy shapes
are turned into the right result or typed error (and therefore the right retry decision),
with no network access. Only the HTTP layer is replayed; LiteLLM and our adapter are real.
"""

from collections.abc import Iterator
from decimal import Decimal

import httpx
import litellm
import pytest
import respx
from pydantic import SecretStr

from app.core.errors import ContentPolicyBlocked, ProviderAuthError, ProviderBadRequest, ProviderError, RateLimited
from app.modules.gateway.plugins.litellm_client import LiteLLMClient
from app.modules.gateway.schemas import Message
from app.modules.registry.schemas import CallTarget, ModelProfileOut, PriceSource, RateLimits
from tests.helpers import provider_fixture

pytestmark = [pytest.mark.integration, pytest.mark.gateway]

PROVIDERS = {
    "openai": (
        "OpenAI",
        "openai/gpt-4o-mini",
        "https://api.openai.com/v1",
        "https://api.openai.com/v1/chat/completions",
    ),
    "anthropic": (
        "Anthropic",
        "anthropic/claude-3-5-haiku-20241022",
        "https://api.anthropic.com",
        "https://api.anthropic.com/v1/messages",
    ),
}

ERROR_CASES = [
    ("openai", "chat_429.json", 429, {"retry-after": "20"}, RateLimited),
    ("openai", "chat_400.json", 400, {}, ProviderBadRequest),
    ("openai", "chat_content_policy.json", 400, {}, ContentPolicyBlocked),
    ("openai", "auth_error.json", 401, {}, ProviderAuthError),
    ("anthropic", "chat_429.json", 429, {"retry-after": "5"}, RateLimited),
    ("anthropic", "chat_400.json", 400, {}, ProviderBadRequest),
    ("anthropic", "auth_error.json", 401, {}, ProviderAuthError),
]


def target(provider: str) -> CallTarget:
    display, model, base, _ = PROVIDERS[provider]
    profile = ModelProfileOut.model_validate(
        {
            "id": "00000000-0000-7000-8000-000000000001",
            "credential_id": "00000000-0000-7000-8000-000000000002",
            "provider": provider,
            "model_name": model.split("/", 1)[1],
            "display_name": model,
            "litellm_model": model,
            "context_window": None,
            "max_output_tokens": None,
            "parameters": {},
            "supports_json_mode": True,
            "supports_system_prompt": True,
            "input_price_per_mtok": Decimal(1),
            "output_price_per_mtok": Decimal(1),
            "price_source": PriceSource.LITELLM,
            "price_known": True,
            "is_selected": True,
        }
    )
    return CallTarget(
        credential_id=profile.credential_id,
        provider=provider,
        provider_display_name=display,
        api_key=SecretStr("sk-recorded-0000"),
        api_base=base,
        profile=profile,
        default_limits=RateLimits(rpm=1, tpm=1),
        override_rpm=None,
        override_tpm=None,
    )


@pytest.fixture
def recorded() -> Iterator[respx.MockRouter]:
    litellm.disable_aiohttp_transport = True
    with respx.mock(assert_all_mocked=True) as mock:
        yield mock


MESSAGES = [Message(role="system", content="Classify."), Message(role="user", content="I was charged twice")]


@pytest.mark.parametrize("provider", sorted(PROVIDERS))
async def test_a_recorded_success_becomes_text_tokens_and_headers(recorded: respx.MockRouter, provider: str) -> None:
    url = PROVIDERS[provider][3]
    headers = {"x-ratelimit-limit-requests": "5000"}
    route = recorded.post(url).mock(
        httpx.Response(200, json=provider_fixture(provider, "chat_success.json"), headers=headers)
    )
    response = await LiteLLMClient().acompletion(target(provider), MESSAGES, {"max_tokens": 5}, timeout_s=5)
    assert route.call_count == 1
    assert response.text == "billing"
    assert response.input_tokens > 0
    assert response.output_tokens > 0


@pytest.mark.parametrize(("provider", "fixture", "status", "headers", "error_type"), ERROR_CASES)
async def test_a_recorded_error_becomes_the_matching_typed_error(
    recorded: respx.MockRouter,
    provider: str,
    fixture: str,
    status: int,
    headers: dict[str, str],
    error_type: type[ProviderError],
) -> None:
    route = recorded.post(PROVIDERS[provider][3]).mock(
        httpx.Response(status, json=provider_fixture(provider, fixture), headers=headers)
    )
    with pytest.raises(ProviderError) as error:
        await LiteLLMClient().acompletion(target(provider), MESSAGES, {}, timeout_s=5)
    assert type(error.value) is error_type
    assert route.call_count == 1
    assert PROVIDERS[provider][0] in error.value.message
    if "retry-after" in headers:
        assert error.value.retry_after_s == float(headers["retry-after"])
