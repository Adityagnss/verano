"""
FastAPI wiring for the project service and the `ProjectScope` dependency.

`ProjectScope` resolves the `{project_id}` path parameter into a `ProjectOut` the caller
is allowed to use, or fails with 404. Every project-scoped router in every module depends
on it, so authorization is written once.
"""

import uuid
from typing import Annotated

from fastapi import Depends

from app.core.database import SessionDep
from app.core.errors import NotFound
from app.core.security import CurrentPrincipal
from app.modules.auth.dependencies import AuthServiceDep
from app.modules.projects.schemas import ProjectOut
from app.modules.projects.service import PROJECT_NOT_FOUND, ProjectService


def get_project_service(session: SessionDep, auth: AuthServiceDep) -> ProjectService:
    return ProjectService(session, auth)


ProjectServiceDep = Annotated[ProjectService, Depends(get_project_service)]


async def project_scope(project_id: uuid.UUID, principal: CurrentPrincipal, service: ProjectServiceDep) -> ProjectOut:
    if principal.project_id is not None and principal.project_id != project_id:
        raise NotFound(PROJECT_NOT_FOUND)
    return await service.require_access(principal, project_id)


ProjectScope = Annotated[ProjectOut, Depends(project_scope)]
