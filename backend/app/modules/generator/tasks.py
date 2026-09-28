"""
Eval Generator background job: generate, clean and draft answers for one draft dataset
version (or regenerate one category). Idempotent; a killed run is recorded as failed.
"""

import uuid

from app.core.container import Container
from app.core.jobs import job
from app.modules.generator.pipeline import GenerationPipeline
from app.modules.generator.schemas import CaseCategory


async def _failed(container: Container, project_id: str, version_id: str, error: str, **_: object) -> None:
    async with container.database.sessions() as session:
        await GenerationPipeline.from_container(session, container).fail(
            uuid.UUID(project_id), uuid.UUID(version_id), error
        )


@job("generator.generate", time_limit_setting="generator_timeout_s", on_failure=_failed)
async def generate(container: Container, project_id: str, version_id: str, regenerate: str | None = None) -> None:
    async with container.database.sessions() as session:
        pipeline = GenerationPipeline.from_container(session, container)
        category = CaseCategory(regenerate) if regenerate else None
        await pipeline.run(uuid.UUID(project_id), uuid.UUID(version_id), category)
