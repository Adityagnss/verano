"""Unit tests for the circuit breaker state machine (clock injected)."""

import pytest

from app.modules.gateway.breaker import CircuitBreaker, CircuitState

pytestmark = pytest.mark.unit


class Clock:
    now = 100.0

    def __call__(self) -> float:
        return self.now


def test_opens_after_threshold_and_isolates_providers() -> None:
    clock = Clock()
    breaker = CircuitBreaker(3, 30.0, clock)
    for _ in range(2):
        breaker.failure("a")
    assert breaker.allow("a") and breaker.state("a") is CircuitState.CLOSED
    breaker.success("a")
    for _ in range(2):
        breaker.failure("a")
    assert breaker.state("a") is CircuitState.CLOSED
    breaker.failure("a")
    assert breaker.state("a") is CircuitState.OPEN and not breaker.allow("a")
    assert breaker.allow("b") and breaker.state("b") is CircuitState.CLOSED
    assert breaker.retry_after("a") == 30.0 and breaker.retry_after("b") == 0.0
    assert breaker.snapshot()["a"] is CircuitState.OPEN


def test_half_open_probe_closes_or_reopens() -> None:
    clock = Clock()
    breaker = CircuitBreaker(1, 30.0, clock)
    breaker.failure("a")
    clock.now += 29
    assert not breaker.allow("a")
    clock.now += 2
    assert breaker.allow("a") and breaker.state("a") is CircuitState.HALF_OPEN
    assert not breaker.allow("a")
    breaker.failure("a")
    assert breaker.state("a") is CircuitState.OPEN and not breaker.allow("a")
    clock.now += 31
    assert breaker.allow("a")
    breaker.release("a")
    assert breaker.allow("a")
    breaker.success("a")
    assert breaker.state("a") is CircuitState.CLOSED and breaker.allow("a")
