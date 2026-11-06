"""
Traffic background jobs: score new traces and check alert rules, and purge traces past their retention.
Both are safe to run twice: scoring claims queued traces with a row lock that skips rows another worker holds, alert
checks never open a second incident for a rule, and a purge deletes only what is already past the cutoff.
"""

import uuid

from app.core.container import Container
from app.core.jobs import job
from app.modules.traffic.alerts import AlertService
from app.modules.traffic.online import OnlineScoringService
from app.modules.traffic.service import TrafficService


@job("traffic.process", time_limit_setting="evaluation_timeout_s")
async def process(container: Container, project_id: str) -> None:
    project = uuid.UUID(project_id)
    async with container.database.sessions() as session:
        await OnlineScoringService(session, container).process(project)
        await session.commit()
    async with container.database.sessions() as session:
        await AlertService(session, container).evaluate(project)
        await session.commit()


@job("traffic.purge")
async def purge(container: Container, project_id: str) -> None:
    async with container.database.sessions() as session:
        await TrafficService(session, container).purge(uuid.UUID(project_id))
        await session.commit()
