"""FastAPI wiring for file ingestion, and the upload-size guard applied before the body is read."""

from typing import Annotated

from fastapi import Depends, Request

from app.core.container import ContainerDep, SettingsDep
from app.core.database import SessionDep
from app.core.storage import FileTooLarge, too_large_message
from app.modules.datasets.ingest import FileIngestService

MULTIPART_OVERHEAD_BYTES = 64 * 1024


def get_ingest_service(session: SessionDep, container: ContainerDep) -> FileIngestService:
    return FileIngestService.from_container(session, container)


def limit_upload_size(request: Request, settings: SettingsDep) -> None:
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > settings.upload_max_bytes + MULTIPART_OVERHEAD_BYTES:
        raise FileTooLarge(too_large_message(settings.upload_max_bytes))


IngestServiceDep = Annotated[FileIngestService, Depends(get_ingest_service)]
UploadGuard = Depends(limit_upload_size)
