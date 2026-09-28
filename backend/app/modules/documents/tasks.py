"""Documents background job: extract an uploaded reference document into sections."""

import uuid

from app.core.container import Container
from app.core.jobs import job
from app.modules.datasets.processing import FileProcessor
from app.modules.documents.service import DocumentService


async def _failed(container: Container, file_id: str, error: str) -> None:
    async with container.database.sessions() as session:
        await FileProcessor.from_container(session, container).fail(uuid.UUID(file_id), "extract", error)


@job("documents.extract", time_limit_setting="file_parse_timeout_s", on_failure=_failed)
async def extract(container: Container, file_id: str) -> None:
    async with container.database.sessions() as session:
        await DocumentService.from_container(session, container).extract(uuid.UUID(file_id))
