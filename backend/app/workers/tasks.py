"""
Celery task entry points, generated from the job registry (`app.core.jobs.JOBS`).

Every module job becomes one Celery task with the same name. A task runs its job in a fresh
event loop with a container built for that run (connection pools are bound to their
loop), and applies the job's time limit: a soft limit that raises inside the job, and a
hard limit a little later that kills a worker stuck in native code. If the job fails for
any reason, including a time limit, its `on_failure` hook records a clear failure.
No business logic lives here. `ping` lets health checks confirm a worker is consuming.
"""

import asyncio
from typing import Any

from celery.exceptions import SoftTimeLimitExceeded
from celery.signals import worker_process_init

from app.core.config import get_settings
from app.core.container import Container
from app.core.jobs import JOBS, JobSpec, load_all_jobs
from app.core.logging import configure_logging
from app.modules.gateway.service import configure_llm_runtime
from app.workers.celery_app import celery_app
from app.workers.queue import CeleryJobQueue

TIME_LIMIT_MESSAGE = "This took longer than the time limit, so it was stopped."
FAILURE_MESSAGE = "Something went wrong while processing this. Try again, and check the worker logs if it repeats."

settings = get_settings()
load_all_jobs()


@worker_process_init.connect
def _configure_process(**_: Any) -> None:
    configure_logging(settings)
    configure_llm_runtime(settings)


async def _call(function: Any, kwargs: dict[str, Any]) -> None:
    container = Container.build(settings, jobs=CeleryJobQueue())
    try:
        await function(container, **kwargs)
    finally:
        await container.close()


def _failure_message(exc: BaseException) -> str:
    message = getattr(exc, "message", None)
    return (
        str(message) if message else TIME_LIMIT_MESSAGE if isinstance(exc, SoftTimeLimitExceeded) else FAILURE_MESSAGE
    )


def _execute(spec: JobSpec, kwargs: dict[str, Any]) -> None:
    try:
        asyncio.run(_call(spec.function, kwargs))
    except BaseException as exc:
        if spec.on_failure is not None:
            asyncio.run(_call(spec.on_failure, {**kwargs, "error": _failure_message(exc)}))
        raise


def _register(name: str, spec: JobSpec) -> None:
    limit = float(getattr(settings, spec.time_limit_setting)) if spec.time_limit_setting else None
    hard = limit + settings.job_hard_limit_grace_s if limit else None

    def run(**kwargs: Any) -> None:
        _execute(spec, kwargs)

    celery_app.task(name=name, soft_time_limit=limit, time_limit=hard)(run)


for job_name, job_spec in JOBS.items():
    _register(job_name, job_spec)


@celery_app.task(name="system.ping")
def ping() -> str:
    return "pong"
