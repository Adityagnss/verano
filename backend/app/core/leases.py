"""
Leases (ADR 0037): how work that a worker is doing proves it is still alive.

A worker that takes a row (a call, a scoring pass, a generation) writes a lease: "mine until this time". While it
works, a heartbeat pushes the time forward. If the worker dies, nobody pushes it, the time passes, and the sweeper
(`app/workers/sweeper.py`) returns the row to pending so another worker finishes it. `Heartbeat` is the pushing half;
`deadline` and `expired` are the pure time rules so they are easy to check.
"""

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from types import TracebackType

log = logging.getLogger(__name__)


def deadline(now: datetime, seconds: float) -> datetime:
    return now + timedelta(seconds=seconds)


def expired(lease_until: datetime | None, now: datetime) -> bool:
    return lease_until is not None and lease_until <= now


class Heartbeat:
    """While the `with` block runs, calls `beat` every `interval_s` seconds. A beat that fails is logged and the
    next one tries again: a missed beat only matters if the lease actually runs out."""

    def __init__(self, beat: Callable[[], Awaitable[None]], interval_s: float) -> None:
        self._beat = beat
        self._interval_s = max(interval_s, 0.01)
        self._task: asyncio.Task[None] | None = None

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self._interval_s)
            try:
                await self._beat()
            except Exception:
                log.warning("lease heartbeat failed; it will try again", exc_info=True)

    async def __aenter__(self) -> "Heartbeat":
        self._task = asyncio.get_running_loop().create_task(self._loop())
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
