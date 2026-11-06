"""
Circuit breaker per provider (ADR 0037). Pure state machine, no I/O, clock injected.

closed     calls go through; consecutive transient failures are counted, a success resets the count.
open       after `threshold` failures in a row calls are refused at once (they would only wait and fail) for
           `open_seconds`. Other providers are not affected: each provider has its own circuit.
half-open  after the wait, exactly one call (the probe) is let through. If it succeeds the circuit closes; if it
           fails the circuit opens again for another full wait.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class Circuit:
    state: CircuitState = CircuitState.CLOSED
    failures: int = 0
    opened_at: float = 0.0
    probing: bool = False


class CircuitBreaker:
    def __init__(self, threshold: int, open_seconds: float, clock: Callable[[], float] = time.monotonic) -> None:
        self.threshold = threshold
        self.open_seconds = open_seconds
        self._clock = clock
        self._circuits: dict[str, Circuit] = {}

    def _get(self, key: str) -> Circuit:
        return self._circuits.setdefault(key, Circuit())

    def allow(self, key: str) -> bool:
        """May a call to this provider go out now? In half-open state only one probe is allowed at a time."""
        circuit = self._get(key)
        if circuit.state is CircuitState.CLOSED:
            return True
        if circuit.state is CircuitState.OPEN:
            if self._clock() - circuit.opened_at < self.open_seconds:
                return False
            circuit.state, circuit.probing = CircuitState.HALF_OPEN, False
        if circuit.probing:
            return False
        circuit.probing = True
        return True

    def success(self, key: str) -> None:
        circuit = self._get(key)
        circuit.state, circuit.failures, circuit.probing = CircuitState.CLOSED, 0, False

    def failure(self, key: str) -> None:
        circuit = self._get(key)
        circuit.probing = False
        if circuit.state is CircuitState.HALF_OPEN:
            circuit.state, circuit.opened_at = CircuitState.OPEN, self._clock()
            return
        circuit.failures += 1
        if circuit.failures >= self.threshold:
            circuit.state, circuit.opened_at = CircuitState.OPEN, self._clock()

    def release(self, key: str) -> None:
        """A probe that ended without telling us anything about the provider (the caller's own mistake, a
        cancelled call) lets the next call probe instead."""
        self._get(key).probing = False

    def state(self, key: str) -> CircuitState:
        return self._get(key).state

    def retry_after(self, key: str) -> float:
        circuit = self._get(key)
        if circuit.state is not CircuitState.OPEN:
            return 0.0
        return max(0.0, self.open_seconds - (self._clock() - circuit.opened_at))

    def snapshot(self) -> dict[str, CircuitState]:
        return {key: circuit.state for key, circuit in self._circuits.items()}
