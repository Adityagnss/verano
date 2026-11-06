"""
LiteLLM adapter: the only code in the platform that calls `litellm.acompletion`.

Sends one attempt to the model with LiteLLM's own retries disabled (the gateway owns
retry policy), and converts the outcome into a `ProviderResponse` or a typed
`ProviderError`. Exceptions are mapped by walking the exception's class hierarchy through
`EXCEPTION_MAP`, so the most specific LiteLLM error wins (for example a content-policy
block is a subclass of a bad request). Response headers are kept for adaptive rate limits.
"""

from typing import Any

import litellm
from litellm import exceptions as llm_errors

from app.core.errors import (
    ContentPolicyBlocked,
    ModelNotFound,
    ProviderAuthError,
    ProviderBadRequest,
    ProviderError,
    ProviderTimeout,
    ProviderUnavailable,
    RateLimited,
    parse_retry_after,
    provider_error,
)
from app.modules.gateway.schemas import Message, ProviderResponse
from app.modules.registry.schemas import CallTarget

EXCEPTION_MAP: dict[type[BaseException], type[ProviderError]] = {
    llm_errors.AuthenticationError: ProviderAuthError,
    llm_errors.PermissionDeniedError: ProviderAuthError,
    llm_errors.ContentPolicyViolationError: ContentPolicyBlocked,
    llm_errors.NotFoundError: ModelNotFound,
    llm_errors.BadRequestError: ProviderBadRequest,
    llm_errors.UnprocessableEntityError: ProviderBadRequest,
    llm_errors.RateLimitError: RateLimited,
    llm_errors.Timeout: ProviderTimeout,
    llm_errors.APIConnectionError: ProviderUnavailable,
    llm_errors.ServiceUnavailableError: ProviderUnavailable,
    llm_errors.InternalServerError: ProviderUnavailable,
    llm_errors.BadGatewayError: ProviderUnavailable,
    llm_errors.APIError: ProviderUnavailable,
}


def configure_litellm() -> None:
    litellm.suppress_debug_info = True
    litellm.telemetry = False
    litellm.drop_params = False


def _headers_of(exc: BaseException) -> dict[str, str]:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None) or getattr(exc, "litellm_response_headers", None) or {}
    return {str(k).lower(): str(v) for k, v in dict(headers).items()}


def map_exception(exc: BaseException, provider: str) -> ProviderError:
    error_cls = next((EXCEPTION_MAP[cls] for cls in type(exc).__mro__ if cls in EXCEPTION_MAP), ProviderUnavailable)
    headers = _headers_of(exc)
    detail = str(getattr(exc, "message", None) or exc)[:500]
    return provider_error(error_cls, provider, detail, parse_retry_after(headers.get("retry-after")), headers)


class LiteLLMClient:
    async def acompletion(
        self, target: CallTarget, messages: list[Message], params: dict[str, Any], timeout_s: float
    ) -> ProviderResponse:
        kwargs: dict[str, Any] = {
            "model": target.profile.litellm_model,
            "messages": [message.model_dump() for message in messages],
            "timeout": timeout_s,
            "num_retries": 0,
            **params,
        }
        if "reasoning_effort" in params:
            kwargs["allowed_openai_params"] = ["reasoning_effort"]
        if target.api_key is not None:
            kwargs["api_key"] = target.api_key.get_secret_value()
        if target.api_base:
            kwargs["api_base"] = target.api_base
        try:
            response = await litellm.acompletion(**kwargs)
        except Exception as exc:
            raise map_exception(exc, target.provider_display_name) from exc
        return self._to_response(response)

    @staticmethod
    def _to_response(response: Any) -> ProviderResponse:
        choice = response.choices[0]
        usage = getattr(response, "usage", None)
        hidden = getattr(response, "_hidden_params", {}) or {}
        reported = getattr(response, "model", None)
        return ProviderResponse(
            text=choice.message.content or "",
            finish_reason=choice.finish_reason,
            input_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
            cached_input_tokens=_detail(usage, "prompt_tokens_details", "cached_tokens"),
            reasoning_tokens=_detail(usage, "completion_tokens_details", "reasoning_tokens"),
            model=(str(reported).strip() or None) if reported else None,
            headers={str(k).lower(): str(v) for k, v in (hidden.get("additional_headers") or {}).items()},
        )


def _detail(usage: Any, group: str, name: str) -> int | None:
    """A token count inside the usage details (cached input, reasoning), or None when not reported."""
    details = getattr(usage, group, None)
    value = details.get(name) if isinstance(details, dict) else getattr(details, name, None)
    return int(value) if isinstance(value, int | float) and not isinstance(value, bool) else None
