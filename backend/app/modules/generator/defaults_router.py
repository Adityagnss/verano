"""Routes for "update checks to the current default set": a preview of the changes, then applying them.
Mounted by the generator router, under /projects/{project_id}."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.container import ContainerDep
from app.core.database import SessionDep
from app.core.security import CurrentPrincipal
from app.modules.generator.defaults_schemas import DefaultsApplied, DefaultsApply, DefaultsPreviewOut
from app.modules.generator.defaults_service import EvaluatorDefaultsService
from app.modules.projects.dependencies import ProjectScope

router = APIRouter(prefix="/evaluator-set-versions/{version_id}", tags=["evaluators"])


def get_defaults_service(session: SessionDep, container: ContainerDep) -> EvaluatorDefaultsService:
    return EvaluatorDefaultsService(session, container.settings)


DefaultsServiceDep = Annotated[EvaluatorDefaultsService, Depends(get_defaults_service)]


@router.get("/default-update")
async def preview_default_update(
    version_id: uuid.UUID, project: ProjectScope, service: DefaultsServiceDep
) -> DefaultsPreviewOut:
    """What updating to the current default checks would add, change and (only if asked) remove. Changes nothing."""
    return await service.preview(project, version_id)


@router.post("/default-update")
async def apply_default_update(
    version_id: uuid.UUID,
    body: DefaultsApply,
    project: ProjectScope,
    principal: CurrentPrincipal,
    service: DefaultsServiceDep,
) -> DefaultsApplied:
    """Apply the update as a new evaluator-set version with a note. Older versions and their runs stay as they were."""
    return await service.apply(project, principal, version_id, body)
