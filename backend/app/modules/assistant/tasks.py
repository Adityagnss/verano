"""
Improve background jobs: analyze failures and start candidate tests (`assistant.improve`),
and move a session on when one of its candidate experiments has been scored
(`assistant.advance`). Both check the session's stage first, so a repeated delivery does
nothing twice.
"""

import uuid

from app.core.container import Container
from app.core.jobs import job
from app.modules.assistant.pipeline import ImprovementPipeline


@job("assistant.improve", time_limit_setting="evaluation_timeout_s")
async def improve(container: Container, session_id: str) -> None:
    async with container.database.sessions() as session:
        await ImprovementPipeline(session, container).improve(uuid.UUID(session_id))


@job("assistant.advance", time_limit_setting="evaluation_timeout_s")
async def advance(container: Container, experiment_id: str) -> None:
    async with container.database.sessions() as session:
        await ImprovementPipeline(session, container).advance(uuid.UUID(experiment_id))
