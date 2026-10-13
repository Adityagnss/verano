"""
Improve background jobs: analyze failures and start candidate tests (`assistant.improve`),
carry on after Stop or a failure (`assistant.resume`), and move a session on when one of its
candidate experiments has been scored (`assistant.advance`). Each checks the session's stage
first, so a repeated delivery does nothing twice, and a job that dies (an error, the time
limit) leaves the session failed with the reason, never hanging on a stage.
"""

import uuid

from app.core.container import Container
from app.core.jobs import job
from app.modules.assistant.pipeline import ImprovementPipeline


async def _failed(container: Container, error: str, session_id: str | None = None, **_: object) -> None:
    if session_id:
        async with container.database.sessions() as session:
            await ImprovementPipeline(session, container).fail(uuid.UUID(session_id), error)


async def _advance_failed(container: Container, error: str, experiment_id: str | None = None, **_: object) -> None:
    if experiment_id:
        async with container.database.sessions() as session:
            await ImprovementPipeline(session, container).fail_for_experiment(uuid.UUID(experiment_id), error)


@job("assistant.improve", time_limit_setting="evaluation_timeout_s", on_failure=_failed)
async def improve(container: Container, session_id: str) -> None:
    async with container.database.sessions() as session:
        await ImprovementPipeline(session, container).improve(uuid.UUID(session_id))


@job("assistant.resume", time_limit_setting="evaluation_timeout_s", on_failure=_failed)
async def resume(container: Container, session_id: str) -> None:
    async with container.database.sessions() as session:
        await ImprovementPipeline(session, container).resume(uuid.UUID(session_id))


@job("assistant.advance", time_limit_setting="evaluation_timeout_s", on_failure=_advance_failed)
async def advance(container: Container, experiment_id: str) -> None:
    async with container.database.sessions() as session:
        await ImprovementPipeline(session, container).advance(uuid.UUID(experiment_id))
