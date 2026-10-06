"""Cached and reasoning token counts are read from the provider's usage details when reported."""

from types import SimpleNamespace

from app.modules.gateway.plugins.litellm_client import LiteLLMClient


def response(usage: object) -> SimpleNamespace:
    choice = SimpleNamespace(message=SimpleNamespace(content="ok"), finish_reason="stop")
    return SimpleNamespace(choices=[choice], usage=usage, model="m")


def test_reported_details_are_kept_and_missing_ones_stay_unknown() -> None:
    usage = SimpleNamespace(
        prompt_tokens=100,
        completion_tokens=40,
        prompt_tokens_details=SimpleNamespace(cached_tokens=60),
        completion_tokens_details={"reasoning_tokens": 30},
    )
    parsed = LiteLLMClient._to_response(response(usage))
    assert (parsed.cached_input_tokens, parsed.reasoning_tokens) == (60, 30)
    bare = LiteLLMClient._to_response(response(SimpleNamespace(prompt_tokens=5, completion_tokens=1)))
    assert (bare.cached_input_tokens, bare.reasoning_tokens) == (None, None)
