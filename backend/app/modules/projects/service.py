"""
Project use cases and the project access check used by every project-scoped route.

Access is decided by organization membership (asked of the auth service). A project in an
organization the user doesn't belong to is reported as not found, so ids can't be probed.
New projects go into the user's personal organization unless another one is named.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFound, PermissionDenied
from app.core.pagination import Page, PageParams, to_page
from app.core.security import Principal
from app.modules.auth.service import AuthService
from app.modules.projects.models import Project
from app.modules.projects.repository import ProjectRepository
from app.modules.projects.schemas import ProjectCreate, ProjectOut

PROJECT_NOT_FOUND = "This project doesn't exist or you don't have access to it."


class ProjectService:
    def __init__(self, session: AsyncSession, auth: AuthService) -> None:
        self._repo = ProjectRepository(session)
        self._auth = auth

    async def create(self, principal: Principal, request: ProjectCreate) -> ProjectOut:
        organization_id = request.organization_id or await self._auth.personal_organization_id(principal.user_id)
        if organization_id not in await self._auth.organization_ids(principal.user_id):
            raise PermissionDenied("You can only create projects in your own workspaces.")
        project = Project(
            organization_id=organization_id,
            name=request.name,
            description=request.description,
            created_by=principal.user_id,
        )
        return ProjectOut.model_validate(await self._repo.add(project))

    async def list_projects(self, principal: Principal, page: PageParams) -> Page[ProjectOut]:
        rows = await self._repo.list_in(await self._auth.organization_ids(principal.user_id), page)
        return to_page([ProjectOut.model_validate(row) for row in rows], page, lambda p: p.id)

    async def require_access(self, principal: Principal, project_id: uuid.UUID) -> ProjectOut:
        project = await self._repo.get_in(project_id, await self._auth.organization_ids(principal.user_id))
        if project is None:
            raise NotFound(PROJECT_NOT_FOUND)
        return ProjectOut.model_validate(project)
