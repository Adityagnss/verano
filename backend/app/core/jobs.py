"""
Background jobs: one registry of job functions, two ways to run them.

A module declares its background work in its `tasks.py` with `@job("module.name")`: an
async function taking the process `Container` plus JSON-serializable keyword arguments.
Every job must be idempotent (safe to run twice), because a job whose worker dies is
delivered again. Services enqueue by name through the `JobQueue` in the container:
- in the API and workers, `CeleryJobQueue` (app/workers) sends it to Celery, which runs it
  with the job's time limit;
- in tests, `InlineJobQueue` runs it on the current event loop, so a test can upload a file
  and then `await queue.drain()` to see the finished result without a worker.
`on_failure` lets a job record a clear failure when it is killed (for example by a hard
time limit), so nothing is left looking "in progress" forever.
"""

import asyncio
import importlib
import pkgutil
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from app.core.registry import Registry

if TYPE_CHECKING:
    from app.core.container import Container

JobFunction = Callable[..., Awaitable[None]]
FailureHook = Callable[..., Awaitable[None]]


@dataclass(frozen=True)
class JobSpec:
    function: JobFunction
    time_limit_setting: str | None
    on_failure: FailureHook | None
    queue: str


JOBS: Registry[JobSpec] = Registry("background job")


def job(
    name: str,
    time_limit_setting: str | None = None,
    on_failure: FailureHook | None = None,
    queue: str = "default",
) -> Callable[[JobFunction], JobFunction]:
    def decorator(function: JobFunction) -> JobFunction:
        JOBS.add(name, JobSpec(function, time_limit_setting, on_failure, queue))
        return function

    return decorator


def load_all_jobs() -> None:
    import app.modules

    for module in pkgutil.iter_modules(app.modules.__path__):
        if importlib.util.find_spec(f"app.modules.{module.name}.tasks"):
            importlib.import_module(f"app.modules.{module.name}.tasks")


class JobQueue(Protocol):
    def enqueue(self, name: str, **kwargs: Any) -> None: ...


class InlineJobQueue:
    def __init__(self) -> None:
        self.container: Container | None = None
        self._pending: list[asyncio.Task[None]] = []

    def enqueue(self, name: str, **kwargs: Any) -> None:
        spec = JOBS[name]
        assert self.container is not None, "InlineJobQueue needs its container before running jobs"
        self._pending.append(asyncio.get_running_loop().create_task(self._run(spec, kwargs)))

    async def _run(self, spec: JobSpec, kwargs: dict[str, Any]) -> None:
        assert self.container is not None
        await spec.function(self.container, **kwargs)

    async def drain(self) -> None:
        while self._pending:
            batch, self._pending = self._pending, []
            await asyncio.gather(*batch)
