"""
Datasets background jobs: profile, validate and import an uploaded rows file. Each job is
idempotent (running it twice gives the same result) and records a clear failure if it is
killed, for example by the parse time limit.
"""

import uuid

from app.core.container import Container
from app.core.jobs import job
from app.modules.datasets.processing import FileProcessor


async def _failed(container: Container, file_id: str, error: str) -> None:
    async with container.database.sessions() as session:
        await FileProcessor.from_container(session, container).fail(uuid.UUID(file_id), "failed", error)


@job("datasets.profile_file", time_limit_setting="file_parse_timeout_s", on_failure=_failed)
async def profile_file(container: Container, file_id: str) -> None:
    async with container.database.sessions() as session:
        processor = FileProcessor.from_container(session, container)
        await processor.run("profile", uuid.UUID(file_id), processor.profile)


@job("datasets.validate_file", time_limit_setting="file_parse_timeout_s", on_failure=_failed)
async def validate_file(container: Container, file_id: str) -> None:
    async with container.database.sessions() as session:
        processor = FileProcessor.from_container(session, container)
        await processor.run("validate", uuid.UUID(file_id), processor.validate)


@job("datasets.import_file", time_limit_setting="file_parse_timeout_s", on_failure=_failed)
async def import_file(container: Container, file_id: str) -> None:
    async with container.database.sessions() as session:
        processor = FileProcessor.from_container(session, container)
        await processor.run("import", uuid.UUID(file_id), processor.import_rows)
