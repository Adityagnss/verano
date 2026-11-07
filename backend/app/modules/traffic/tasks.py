"""
Traffic background jobs: score new traces and check alert rules, and purge traces past their retention.
Both are safe to run twice: scoring claims queued traces with a row lock that skips rows another worker holds, alert
checks never open a second incident for a rule, and a purge deletes only what is already past the cutoff.
"""

import uuid

from app.core.container import Container
from app.core.jobs import job
from app.modules.traffic.alerts import AlertService
from app.modules.traffic.ingest import PROCESS_JOB, PURGE_JOB
from app.modules.traffic.online import OnlineScoringService
from app.modules.traffic.repository import TrafficRepository
from app.modules.traffic.service import TrafficService


@job("traffic.sweep")
async def sweep(container: Container) -> None:
    """Runs on a timer (Celery beat): starts scoring, alert checks and the purge for every project that holds traffic,
    so they happen without incoming traffic too. Uses the same once-per-interval keys as the receiver, so a project
    that is also receiving is not started twice."""
    settings = container.settings
    async with container.database.sessions() as session:
        projects = await TrafficRepository(session).project_ids_with_traffic()
    for project in projects:
        if await container.valkey.set(
            f"traffic:process:{project}", "1", nx=True, ex=settings.traffic_process_interval_s
        ):
            container.jobs.enqueue(PROCESS_JOB, project_id=str(project))
        if await container.valkey.set(f"traffic:purge:{project}", "1", nx=True, ex=3600):
            container.jobs.enqueue(PURGE_JOB, project_id=str(project))


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
