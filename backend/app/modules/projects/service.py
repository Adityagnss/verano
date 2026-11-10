"""
Project use cases and the project access check used by every project-scoped route.

Access is decided by organization membership (asked of the auth service). A project in an
organization the user doesn't belong to is reported as not found, so ids can't be probed.
New projects go into the user's personal organization unless another one is named.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflict, NotFound, PermissionDenied, ValidationFailed
from app.core.pagination import Page, PageParams, to_page
from app.core.permissions import Action, role_allows
from app.core.security import Principal
from app.modules.auth.service import AuthService
from app.modules.projects.models import Project
from app.modules.projects.repository import ProjectRepository
from app.modules.projects.schemas import ProjectCreate, ProjectOut, ProjectRename

PROJECT_NOT_FOUND = "This project doesn't exist or you don't have access to it."
DUPLICATE_NAME = "You already have a project with this name. Pick another name, or open the existing one."


class ProjectService:
    def __init__(self, session: AsyncSession, auth: AuthService) -> None:
        self._repo = ProjectRepository(session)
        self._auth = auth

    async def create(self, principal: Principal, request: ProjectCreate) -> ProjectOut:
        organization_id = request.organization_id or await self._auth.personal_organization_id(principal.user_id)
        role = await self._auth.role_in(principal.user_id, organization_id)
        if role is None:
            raise PermissionDenied("You can only create projects in your own workspaces.")
        if not role_allows(role, Action.WRITE):
            raise PermissionDenied(f"Your role in this workspace ({role.value}) can't create projects.")
        name = request.name.strip()
        if not name:
            raise ValidationFailed("Give the project a name.")
        if await self._repo.name_taken(organization_id, name):
            raise Conflict(DUPLICATE_NAME)
        project = Project(
            organization_id=organization_id,
            name=name,
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

    async def rename(self, principal: Principal, project: ProjectOut, request: ProjectRename) -> ProjectOut:
        await self._require(principal, project, Action.WRITE, "rename")
        name = request.name.strip()
        if not name:
            raise ValidationFailed("Give the project a name.")
        if await self._repo.name_taken(project.organization_id, name, except_id=project.id):
            raise Conflict(DUPLICATE_NAME)
        renamed = await self._repo.rename(project.id, name)
        if renamed is None:
            raise NotFound(PROJECT_NOT_FOUND)
        return ProjectOut.model_validate(renamed)

    async def delete(self, principal: Principal, project: ProjectOut) -> None:
        """Remove the project and everything in it (every table cascades from `projects`)."""
        await self._require(principal, project, Action.DELETE, "delete")
        await self._repo.remove(project.id)

    async def _require(self, principal: Principal, project: ProjectOut, action: Action, verb: str) -> None:
        role = await self._auth.role_in(principal.user_id, project.organization_id)
        if role is None or not role_allows(role, action):
            raise PermissionDenied(f"Your role in this workspace can't {verb} projects.")
