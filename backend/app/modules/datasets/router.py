"""
Input-file HTTP routes: upload (golden set / input files / reference documents), list,
inspect, delete, choose a sheet, suggest and confirm a column mapping, import, and the
live progress stream (Server-Sent Events) for whatever the file is going through.
"""

import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile, status
from fastapi.responses import StreamingResponse

from app.core.events import sse_response
from app.core.pagination import Page, PageDep
from app.core.security import CurrentPrincipal
from app.core.storage import CHUNK_BYTES
from app.modules.datasets.dependencies import IngestServiceDep, UploadGuard
from app.modules.datasets.schemas import (
    InputFileOut,
    MappingRequest,
    MappingSuggestion,
    SheetRequest,
    UploadPurpose,
    VariableMappingRequest,
)
from app.modules.projects.dependencies import ProjectScope

router = APIRouter(prefix="/projects/{project_id}/input-files", tags=["datasets"])
FILE = "/{file_id}"


async def _chunks(upload: UploadFile) -> AsyncIterator[bytes]:
    while chunk := await upload.read(CHUNK_BYTES):
        yield chunk


@router.post("", status_code=status.HTTP_201_CREATED, dependencies=[UploadGuard])
async def upload_file(
    project: ProjectScope,
    principal: CurrentPrincipal,
    service: IngestServiceDep,
    file: Annotated[UploadFile, File()],
    purpose: Annotated[UploadPurpose, Form()],
) -> InputFileOut:
    filename = file.filename or "upload"
    content_type = file.content_type or "application/octet-stream"
    return await service.upload(project, principal, purpose, filename, content_type, _chunks(file))


@router.get("")
async def list_files(project: ProjectScope, service: IngestServiceDep, page: PageDep) -> Page[InputFileOut]:
    return await service.list_files(project, page)


@router.get(FILE)
async def get_file(file_id: uuid.UUID, project: ProjectScope, service: IngestServiceDep) -> InputFileOut:
    return await service.get_file(project, file_id)


@router.delete(FILE, status_code=status.HTTP_204_NO_CONTENT)
async def delete_file(file_id: uuid.UUID, project: ProjectScope, service: IngestServiceDep) -> None:
    await service.delete_file(project, file_id)


@router.get(f"{FILE}/events")
async def file_events(file_id: uuid.UUID, project: ProjectScope, service: IngestServiceDep) -> StreamingResponse:
    return sse_response(await service.progress(project, file_id))


@router.put(f"{FILE}/sheet")
async def select_sheet(
    file_id: uuid.UUID, body: SheetRequest, project: ProjectScope, service: IngestServiceDep
) -> InputFileOut:
    return await service.select_sheet(project, file_id, body.sheet)


@router.get(f"{FILE}/mapping-suggestion")
async def suggest_mapping(file_id: uuid.UUID, project: ProjectScope, service: IngestServiceDep) -> MappingSuggestion:
    return await service.suggest_mapping(project, file_id)


@router.put(f"{FILE}/mapping")
async def submit_mapping(
    file_id: uuid.UUID, body: MappingRequest, project: ProjectScope, service: IngestServiceDep
) -> InputFileOut:
    return await service.submit_mapping(project, file_id, body)


@router.put(f"{FILE}/variables")
async def set_variables(
    file_id: uuid.UUID, body: VariableMappingRequest, project: ProjectScope, service: IngestServiceDep
) -> InputFileOut:
    return await service.set_variables(project, file_id, body)


@router.post(f"{FILE}/import")
async def import_file(file_id: uuid.UUID, project: ProjectScope, service: IngestServiceDep) -> InputFileOut:
    return await service.start_import(project, file_id)
