"""Security background job: write the attack cases of one pack (idempotent; a killed job marks the pack failed)."""

import uuid

from app.core.container import Container
from app.core.jobs import job
from app.modules.security.pipeline import SecurityPipeline


async def _failed(container: Container, pack_id: str, error: str, **_: object) -> None:
    async with container.database.sessions() as session:
        await SecurityPipeline(session, container).fail(uuid.UUID(pack_id), error)


@job("security.generate", time_limit_setting="generator_timeout_s", on_failure=_failed)
async def generate(container: Container, pack_id: str) -> None:
    async with container.database.sessions() as session:
        await SecurityPipeline(session, container).generate(uuid.UUID(pack_id))
