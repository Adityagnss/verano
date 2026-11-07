"""
Integration tests for the circuit breaker (S9.9): a provider that keeps failing is paused for a while, another provider
carries on, a probe call closes the circuit again, the experiment executor puts refused calls back to pending and pauses
the run, and /provider-health reports it.
"""

import uuid
from typing import Any

import httpx
import pytest

from app.core.config import Settings
from app.core.container import Container
from app.core.errors import CircuitOpen, ProviderError
from app.core.jobs import InlineJobQueue
from app.modules.gateway.breaker import CircuitBreaker, CircuitState
from app.modules.gateway.plugins.rate_limiter import ValkeyRateLimiter
from app.modules.gateway.schemas import CallContext, CallPurpose, Message
from app.modules.gateway.service import GatewayService, adaptive_policy
from app.modules.registry.service import RegistryService
from tests.helpers import Session, add_credential, approved_project

pytestmark = [pytest.mark.integration, pytest.mark.gateway]


class Clock:
    now = 1_000.0

    def __call__(self) -> float:
        return self.now


async def no_sleep(seconds: float) -> None:
    return None


async def test_the_circuit_opens_other_providers_continue_and_a_probe_closes_it(
    client: httpx.AsyncClient, session: Session, container: Container, settings: Settings
) -> None:
    credential = await add_credential(client, session, "mock")
    clock = Clock()
    breaker = CircuitBreaker(2, 30.0, clock)
    limiter = ValkeyRateLimiter(
        container.valkey,
        adaptive_policy(settings),
        settings.rate_limit_acquire_timeout_s,
        settings.rate_limit_state_ttl_s,
    )
    context = CallContext(project_id=session.project_id)
    messages = [Message(role="user", content="hi")]
    async with container.database.sessions() as db:
        registry = RegistryService(db, container)
        gateway = GatewayService(
            registry,
            limiter,
            container.database.sessions,
            settings,
            sleep=no_sleep,
            jitter=lambda: 0.0,
            breaker=breaker,
        )
        cred = uuid.UUID(credential["id"])
        with pytest.raises((ProviderError, CircuitOpen)):
            await gateway.complete("down", messages, {}, cred, CallPurpose.TEST_RUN, context)
        assert breaker.state("mock") is CircuitState.OPEN  # two failures in a row inside one call's retries

        with pytest.raises(CircuitOpen) as refused:
            await gateway.complete("echo", messages, {}, cred, CallPurpose.TEST_RUN, context)
        assert "pausing" in refused.value.message.lower() or "paus" in refused.value.message.lower()

        target = await registry.call_target(session.project_id, cred, "echo")
        other = target.model_copy(update={"provider": "other-provider"})
        result = await gateway.complete_target(other, messages, {}, CallPurpose.TEST_RUN, context)
        assert result.text == "hi" and breaker.state("other-provider") is CircuitState.CLOSED

        clock.now += 31
        probe = await gateway.complete("echo", messages, {}, cred, CallPurpose.TEST_RUN, context)
        assert probe.text == "hi" and breaker.state("mock") is CircuitState.CLOSED


async def test_the_executor_puts_refused_calls_back_pauses_the_run_and_health_reports_it(
    client: httpx.AsyncClient,
    session: Session,
    jobs: InlineJobQueue,
    container: Container,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(container.settings, "breaker_failure_threshold", 2)
    monkeypatch.setattr(container.settings, "llm_backoff_base_s", 0.001)
    monkeypatch.setattr(container.settings, "llm_backoff_max_s", 0.002)
    models = await approved_project(client, session, jobs)
    base = f"/api/v1/projects/{session.project_id}"
    body: dict[str, Any] = {"models": [{"model_profile_id": models["down"], "runs": 1}]}
    started = await client.post(f"{base}/experiments", json=body, headers=session.headers)
    assert started.status_code == 201, started.text
    await jobs.drain()
    done = (await client.get(f"{base}/experiments/{started.json()['id']}", headers=session.headers)).json()
    assert done["status"] == "paused"
    assert "paus" in done["stop_reason"].lower()
    progress = done["progress"][0]
    assert progress["failed"] == 0 and progress["succeeded"] == 0  # refused calls were never made, so none failed
    health = await client.get("/api/v1/provider-health", headers=session.headers)
    assert health.status_code == 200 and health.json() == {"mock": "open"}
    assert (await client.get("/api/v1/provider-health")).status_code == 401
