"""Project HTTP routes."""

from fastapi import APIRouter, status

from app.core.pagination import Page, PageDep
from app.core.security import CurrentPrincipal
from app.modules.projects.dependencies import ProjectScope, ProjectServiceDep
from app.modules.projects.schemas import ProjectCreate, ProjectOut

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_project(body: ProjectCreate, principal: CurrentPrincipal, service: ProjectServiceDep) -> ProjectOut:
    return await service.create(principal, body)


@router.get("")
async def list_projects(principal: CurrentPrincipal, service: ProjectServiceDep, page: PageDep) -> Page[ProjectOut]:
    return await service.list_projects(principal, page)


@router.get("/{project_id}")
async def get_project(project: ProjectScope) -> ProjectOut:
    return project
