"""
LLM Gateway: the single path every LLM call in the platform takes.

`complete` runs the six steps from DEVELOPMENT.md 1.4 for one logical call:
filter parameters against the model profile → acquire a rate-limit slot → call LiteLLM →
retry 429s / 5xx / timeouts / connection errors with backoff and jitter (never 400, 401 or
content-policy blocks) → compute tokens and cost → record one `LLMCall` row.
`complete_json` adds structured output on top: JSON mode when the profile supports it,
fence/prose stripping, Pydantic validation, one repair attempt with the validation error,
then a clear `StructuredOutputError` that points at the recorded raw output. No other
module parses model JSON.
Records are written in their own session so spend is never lost with a caller's rollback.
"""

import asyncio
import json
import random
import secrets
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.errors import AppError, CircuitOpen, ProviderError, RateLimited, StructuredOutputError
from app.core.security import utcnow
from app.core.templates import render_system_prompt
from app.core.tokens import estimate_tokens
from app.modules.gateway.breaker import CircuitBreaker
from app.modules.gateway.domain import (
    AdaptivePolicy,
    FilteredParams,
    PendingCall,
    allowed_parameters,
    backoff_delay,
    compute_cost,
    filter_params,
    parse_json,
    parse_rate_headers,
    should_retry,
    with_instruction,
)
from app.modules.gateway.plugins.litellm_client import LiteLLMClient, configure_litellm
from app.modules.gateway.plugins.mock_provider import install_mock_provider
from app.modules.gateway.plugins.rate_limiter import ValkeyRateLimiter
from app.modules.gateway.repository import LLMCallRepository
from app.modules.gateway.schemas import (
    CallContext,
    CallPurpose,
    CallStatus,
    LLMResult,
    Message,
    ProviderResponse,
)
from app.modules.registry.schemas import CallTarget
from app.modules.registry.service import RegistryService

M = TypeVar("M", bound=BaseModel)
PROMPTS_DIR = Path(__file__).parent / "prompts"
CIRCUIT_OPEN = (
    "{provider} has been failing, so calls to it are paused for about {seconds} seconds. "
    "Other providers are not affected. Resume or retry once it answers again."
)
_BREAKER: CircuitBreaker | None = None


def breaker_for(settings: Settings) -> CircuitBreaker:
    """One circuit breaker per process (a gateway is built per request or job; the provider's health is not)."""
    global _BREAKER
    if _BREAKER is None:
        _BREAKER = CircuitBreaker(settings.breaker_failure_threshold, settings.breaker_open_seconds)
    return _BREAKER


def configure_llm_runtime(settings: Settings) -> None:
    configure_litellm()
    if settings.mock_provider_enabled:
        install_mock_provider(settings)


def adaptive_policy(settings: Settings) -> AdaptivePolicy:
    return AdaptivePolicy(
        decrease_factor=settings.rate_limit_decrease_factor,
        increase_fraction=settings.rate_limit_increase_fraction,
        floor_fraction=settings.rate_limit_floor_fraction,
    )


class GatewayService:
    def __init__(
        self,
        registry: RegistryService,
        limiter: ValkeyRateLimiter,
        sessions: async_sessionmaker[AsyncSession],
        settings: Settings,
        client: LiteLLMClient | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        jitter: Callable[[], float] = random.random,
        clock: Callable[[], datetime] = utcnow,
        breaker: CircuitBreaker | None = None,
    ) -> None:
        self._registry = registry
        self._limiter = limiter
        self._sessions = sessions
        self._settings = settings
        self._client = client or LiteLLMClient()
        self._sleep = sleep
        self._jitter = jitter
        self._clock = clock
        self._breaker = breaker or breaker_for(settings)

    async def complete(
        self,
        model_id: str,
        messages: list[Message],
        params: dict[str, Any],
        credential_id: uuid.UUID,
        purpose: CallPurpose,
        context: CallContext,
    ) -> LLMResult:
        target = await self._registry.call_target(context.project_id, credential_id, model_id)
        return await self.complete_target(target, messages, params, purpose, context)

    async def complete_target(
        self,
        target: CallTarget,
        messages: list[Message],
        params: dict[str, Any],
        purpose: CallPurpose,
        context: CallContext,
    ) -> LLMResult:
        """`complete` for a target resolved beforehand, so no database transaction stays open during the call."""
        json_param = self._registry.catalog.json_mode_parameter
        filtered = filter_params(params, allowed_parameters(target.profile, json_param))
        return await self._run(target, messages, filtered, purpose, context)

    async def complete_json(
        self,
        model_id: str,
        messages: list[Message],
        schema: type[M],
        credential_id: uuid.UUID,
        purpose: CallPurpose,
        context: CallContext,
        params: dict[str, Any] | None = None,
    ) -> M:
        target = await self._registry.call_target(context.project_id, credential_id, model_id)
        return await self.complete_json_target(target, messages, schema, purpose, context, params)

    async def complete_json_target(
        self,
        target: CallTarget,
        messages: list[Message],
        schema: type[M],
        purpose: CallPurpose,
        context: CallContext,
        params: dict[str, Any] | None = None,
    ) -> M:
        """`complete_json` for a target resolved beforehand (no transaction open during the call)."""
        json_param = self._registry.catalog.json_mode_parameter
        request_params = dict(params or {})
        if target.profile.supports_json_mode:
            request_params[json_param] = {"type": "json_object"}
        filtered = filter_params(request_params, allowed_parameters(target.profile, json_param))
        instruction = render_system_prompt(
            PROMPTS_DIR, "json_instruction.jinja", schema=json.dumps(schema.model_json_schema())
        )
        conversation = with_instruction(messages, instruction, target.profile.supports_system_prompt)
        call_ids: list[uuid.UUID] = []
        error = ""
        for _ in range(1 + self._settings.json_repair_attempts):
            result = await self._run(target, conversation, filtered, purpose, context)
            call_ids.append(result.call_id)
            try:
                return schema.model_validate(parse_json(result.text))
            except (ValueError, ValidationError) as exc:
                error = str(exc)[:1000]
                repair = render_system_prompt(PROMPTS_DIR, "json_repair.jinja", error=error)
                conversation = [
                    *conversation,
                    Message(role="assistant", content=result.text),
                    Message(role="user", content=repair),
                ]
        raise StructuredOutputError(
            f"{target.profile.display_name} did not return valid JSON for {schema.__name__}, "
            "even after a repair attempt.",
            {"llm_call_ids": [str(call_id) for call_id in call_ids], "last_error": error, "raw_output": result.text},
        )

    async def _run(
        self,
        target: CallTarget,
        messages: list[Message],
        filtered: FilteredParams,
        purpose: CallPurpose,
        context: CallContext,
    ) -> LLMResult:
        call = PendingCall(
            target=target,
            messages=messages,
            filtered=filtered,
            purpose=purpose,
            context=context,
            started_at=self._clock(),
            trace_id=context.trace_id or secrets.token_hex(16),
            span_id=secrets.token_hex(8),
            estimated_tokens=estimate_tokens(
                (message.content for message in messages),
                filtered.sent.get("max_tokens"),
                self._settings.token_estimate_chars_per_token,
            ),
        )
        while True:
            call.attempts += 1
            provider = target.provider
            if not self._breaker.allow(provider):
                refused = CircuitOpen(
                    CIRCUIT_OPEN.format(
                        provider=target.provider_display_name, seconds=round(self._breaker.retry_after(provider)) or 1
                    ),
                    retry_after_s=self._breaker.retry_after(provider),
                )
                raise refused
            try:
                response, latency_ms = await self._attempt(call)
            except ProviderError as error:
                if isinstance(error, RateLimited):
                    await self._limiter.record_throttle(target, error.retry_after_s)
                    self._breaker.release(provider)
                elif error.retryable:
                    self._breaker.failure(provider)
                else:
                    self._breaker.release(provider)
                if not should_retry(error, call.attempts, self._settings.llm_max_attempts):
                    await self._record_failure(call, error)
                    raise
                await self._sleep(self._backoff(call.attempts, error))
                continue
            except BaseException:
                self._breaker.release(provider)
                raise
            self._breaker.success(provider)
            return await self._record_success(call, response, latency_ms)

    async def _attempt(self, call: PendingCall) -> tuple[ProviderResponse, int]:
        await self._limiter.acquire(call.target, call.estimated_tokens)
        began = time.perf_counter()
        response = await self._client.acompletion(
            call.target,
            call.messages,
            call.filtered.sent,
            self._settings.assistant_timeout_s
            if call.purpose is CallPurpose.ASSISTANT
            else self._settings.llm_timeout_s,
        )
        return response, int((time.perf_counter() - began) * 1000)

    def _backoff(self, attempt: int, error: ProviderError) -> float:
        return backoff_delay(
            attempt,
            error.retry_after_s,
            self._settings.llm_backoff_base_s,
            self._settings.llm_backoff_max_s,
            self._jitter(),
        )

    async def _record_success(self, call: PendingCall, response: ProviderResponse, latency_ms: int) -> LLMResult:
        target, profile = call.target, call.target.profile
        headers = parse_rate_headers(response.headers, self._registry.rate_limit_headers())
        await self._limiter.record_success(
            target, headers, call.estimated_tokens, response.input_tokens + response.output_tokens
        )
        cost = compute_cost(
            response.input_tokens, response.output_tokens, profile.input_price_per_mtok, profile.output_price_per_mtok
        )
        outcome = {
            "status": CallStatus.SUCCEEDED,
            "response_model": response.model,
            "output_text": response.text,
            "finish_reason": response.finish_reason,
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
            "cached_input_tokens": response.cached_input_tokens,
            "reasoning_tokens": response.reasoning_tokens,
            "cost": cost,
            "latency_ms": latency_ms,
        }
        call_id = await self._record(call.record(self._clock()) | outcome)
        return LLMResult(
            call_id=call_id,
            text=response.text,
            finish_reason=response.finish_reason,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            cost=cost,
            latency_ms=latency_ms,
            attempts=call.attempts,
            model=profile.litellm_model,
            response_model=response.model,
            provider=target.provider,
            params=call.filtered.sent,
            trace_id=call.trace_id,
            span_id=call.span_id,
        )

    async def _record_failure(self, call: PendingCall, error: AppError) -> None:
        outcome = {"status": CallStatus.FAILED, "error_type": error.code, "error_message": error.message}
        call_id = await self._record(call.record(self._clock()) | outcome)
        error.details["llm_call_id"] = str(call_id)

    async def _record(self, values: dict[str, Any]) -> uuid.UUID:
        async with self._sessions() as session:
            call_id = await LLMCallRepository(session).add(values)
            await session.commit()
        return call_id
