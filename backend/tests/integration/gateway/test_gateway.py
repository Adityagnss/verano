"""
Integration tests for the LLM gateway on the mock provider: recording, parameter
filtering, cost, retry policy, adaptive rate limits and structured output.

Retry and limiter waits run on a fake clock: sleeping advances the clock instantly, so
the tests assert the exact waits the gateway chose without ever really sleeping.
"""

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import httpx
import pytest
from pydantic import BaseModel
from sqlalchemy import select

from app.core.config import Settings
from app.core.container import Container
from app.core.errors import (
    AppError,
    ContentPolicyBlocked,
    ProviderAuthError,
    ProviderBadRequest,
    RateLimited,
    StructuredOutputError,
)
from app.modules.gateway.models import LLMCall
from app.modules.gateway.plugins.rate_limiter import ValkeyRateLimiter
from app.modules.gateway.schemas import CallContext, CallPurpose, Message
from app.modules.gateway.service import GatewayService, adaptive_policy
from app.modules.registry.service import RegistryService
from tests.helpers import Session, add_credential

pytestmark = [pytest.mark.integration, pytest.mark.gateway]


@dataclass
class FakeClock:
    now_s: float = 1_000_000.0
    sleeps: list[float] = field(default_factory=list)

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(round(seconds, 3))
        self.now_s += seconds

    def now_ms(self) -> float:
        return self.now_s * 1000


@dataclass
class Harness:
    gateway: GatewayService
    limiter: ValkeyRateLimiter
    registry: RegistryService
    clock: FakeClock
    credential_id: uuid.UUID
    context: CallContext

    async def call(self, model: str, content: str, **params: Any) -> Any:
        messages = [Message(role="user", content=content)]
        return await self.gateway.complete(
            model, messages, params, self.credential_id, CallPurpose.TEST_RUN, self.context
        )


class Triage(BaseModel):
    label: str
    confidence: float


@pytest.fixture
async def harness(
    client: httpx.AsyncClient, session: Session, container: Container, settings: Settings
) -> AsyncIterator[Harness]:
    credential = await add_credential(client, session, "mock")
    clock = FakeClock()
    limiter = ValkeyRateLimiter(
        container.valkey,
        adaptive_policy(settings),
        settings.rate_limit_acquire_timeout_s,
        settings.rate_limit_state_ttl_s,
        sleep=clock.sleep,
        now_ms=clock.now_ms,
    )
    async with container.database.sessions() as db:
        registry = RegistryService(db, container)
        gateway = GatewayService(
            registry, limiter, container.database.sessions, settings, sleep=clock.sleep, jitter=lambda: 0.0
        )
        yield Harness(
            gateway, limiter, registry, clock, uuid.UUID(credential["id"]), CallContext(project_id=session.project_id)
        )


async def recorded_calls(container: Container) -> list[LLMCall]:
    async with container.database.sessions() as db:
        return list((await db.scalars(select(LLMCall).order_by(LLMCall.id))).all())


async def test_a_call_is_recorded_with_exactly_the_params_sent_its_tokens_and_its_cost(
    client: httpx.AsyncClient, session: Session, container: Container
) -> None:
    credential = await add_credential(client, session, "mock")
    body = {
        "credential_id": credential["id"],
        "model": "echo",
        "messages": [{"role": "user", "content": "hello gateway"}],
        "params": {"temperature": 0.3, "max_tokens": 20, "logit_bias": {"42": 5}},
    }
    response = await client.post(f"/api/v1/projects/{session.project_id}/llm-calls", json=body, headers=session.headers)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["text"] == "hello gateway"
    assert result["params"] == {"temperature": 0.3, "max_tokens": 20}
    assert (result["input_tokens"], result["output_tokens"], result["attempts"]) == (4, 4, 1)
    assert Decimal(result["cost"]) == Decimal("0.000008")

    [call] = await recorded_calls(container)
    assert (call.status, call.purpose, call.model) == ("succeeded", "test_run", "mock/echo")
    assert call.params == {"temperature": 0.3, "max_tokens": 20}
    assert call.labels["dropped_params"] == "logit_bias"
    assert call.request_messages == [{"role": "user", "content": "hello gateway"}]
    summary = await client.get(f"/api/v1/projects/{session.project_id}/llm-calls/summary", headers=session.headers)
    assert (Decimal(summary.json()["cost"]), summary.json()["calls"]) == (Decimal("0.000008"), 1)


async def test_an_out_of_range_parameter_is_rejected_before_any_call_is_made(
    client: httpx.AsyncClient, session: Session, container: Container
) -> None:
    credential = await add_credential(client, session, "mock")
    body = {
        "credential_id": credential["id"],
        "model": "echo",
        "messages": [{"role": "user", "content": "hi"}],
        "params": {"temperature": 9},
    }
    response = await client.post(f"/api/v1/projects/{session.project_id}/llm-calls", json=body, headers=session.headers)
    assert (response.status_code, response.json()["error"]["code"]) == (422, "invalid_parameter")
    assert await recorded_calls(container) == []


async def test_a_429_is_retried_after_its_retry_after_and_a_500_with_backoff_then_the_call_succeeds(
    harness: Harness, container: Container
) -> None:
    result = await harness.call("recovering", "please recover")
    assert (result.text, result.attempts) == ("please recover", 3)
    assert harness.clock.sleeps == [2.5, 0.5]
    [call] = await recorded_calls(container)
    assert (call.status, call.attempts) == ("succeeded", 3)


async def test_a_timeout_is_retried(harness: Harness) -> None:
    assert (await harness.call("timeouts", "slow start")).attempts == 2


async def test_a_429_storm_uses_every_attempt_then_fails_with_a_recorded_error(
    harness: Harness, container: Container
) -> None:
    with pytest.raises(RateLimited) as error:
        await harness.call("storm", "everyone at once")
    assert harness.clock.sleeps == [4.0, 4.0]
    [call] = await recorded_calls(container)
    assert (call.status, call.attempts, call.error_type) == ("failed", 3, "rate_limited")
    assert error.value.details["llm_call_id"] == str(call.id)
    limits = await harness.limiter.limits(
        await harness.registry.call_target(harness.context.project_id, harness.credential_id, "storm")
    )
    assert limits.rpm.current < limits.rpm.ceiling


@pytest.mark.parametrize(
    ("model", "error_type"),
    [("unauthorized", ProviderAuthError), ("rejected", ProviderBadRequest), ("blocked", ContentPolicyBlocked)],
)
async def test_auth_errors_bad_requests_and_content_policy_blocks_are_never_retried(
    harness: Harness, container: Container, model: str, error_type: type[AppError]
) -> None:
    with pytest.raises(error_type):
        await harness.call(model, "no second chances")
    assert harness.clock.sleeps == []
    [call] = await recorded_calls(container)
    assert (call.status, call.attempts) == ("failed", 1)


async def test_the_limiter_makes_callers_wait_once_the_credentials_request_budget_is_spent(
    client: httpx.AsyncClient, session: Session, harness: Harness
) -> None:
    await client.patch(
        f"/api/v1/projects/{session.project_id}/credentials/{harness.credential_id}",
        json={"rpm_limit": 2},
        headers=session.headers,
    )
    target = await harness.registry.call_target(harness.context.project_id, harness.credential_id, "echo")
    waits = [await harness.limiter.acquire(target, tokens=10) for _ in range(3)]
    assert waits == [0.0, 0.0, 30_000.0]


async def test_provider_rate_headers_raise_the_ceiling_and_a_429_cuts_the_rate(harness: Harness) -> None:
    await harness.call("reporting", "what are my limits?")
    target = await harness.registry.call_target(harness.context.project_id, harness.credential_id, "reporting")
    learned = await harness.limiter.limits(target)
    assert (learned.rpm.ceiling, learned.rpm.current) == (900, 900)
    await harness.limiter.record_throttle(target, retry_after_s=None)
    assert (await harness.limiter.limits(target)).rpm.current == 450


async def json_call(harness: Harness, case: str) -> Triage:
    messages = [Message(role="system", content="Classify the ticket."), Message(role="user", content=f"case:{case}")]
    return await harness.gateway.complete_json(
        "scripted", messages, Triage, harness.credential_id, CallPurpose.GENERATION, harness.context
    )


async def test_complete_json_extracts_json_wrapped_in_prose_and_code_fences(
    harness: Harness, container: Container
) -> None:
    assert await json_call(harness, "wrapped") == Triage(label="shipping", confidence=0.75)
    [call] = await recorded_calls(container)
    assert call.params == {"response_format": {"type": "json_object"}}
    assert "JSON Schema" in call.request_messages[0]["content"]


async def test_complete_json_repairs_once_by_sending_back_the_validation_error(
    harness: Harness, container: Container
) -> None:
    assert await json_call(harness, "repairable") == Triage(label="billing", confidence=0.9)
    first, repair = await recorded_calls(container)
    assert repair.request_messages[-2] == {"role": "assistant", "content": first.output_text}
    assert "could not be used" in repair.request_messages[-1]["content"]
    assert "confidence" in repair.request_messages[-1]["content"]


async def test_complete_json_fails_clearly_and_keeps_the_raw_output_when_it_cannot_recover(
    harness: Harness, container: Container
) -> None:
    with pytest.raises(StructuredOutputError) as error:
        await json_call(harness, "hopeless")
    calls = await recorded_calls(container)
    assert error.value.details["llm_call_ids"] == [str(call.id) for call in calls]
    assert len(calls) == 2
    assert all(call.output_text == "I'm sorry, I can only answer in plain English." for call in calls)
