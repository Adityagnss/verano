"""Reference-document HTTP routes: the sections extracted from an uploaded document."""

import uuid

from fastapi import APIRouter

from app.core.pagination import Page, PageDep
from app.modules.documents.dependencies import DocumentServiceDep
from app.modules.documents.schemas import SectionOut
from app.modules.projects.dependencies import ProjectScope

router = APIRouter(prefix="/projects/{project_id}/input-files", tags=["documents"])


@router.get("/{file_id}/sections")
async def list_sections(
    file_id: uuid.UUID, project: ProjectScope, service: DocumentServiceDep, page: PageDep
) -> Page[SectionOut]:
    return await service.sections(project, file_id, page)
