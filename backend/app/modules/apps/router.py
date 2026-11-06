"""Apps HTTP routes: add, list, change, remove and try an app that Verano tests over HTTP."""

import uuid

from fastapi import APIRouter, Depends, status

from app.core.features import APPS, require_feature
from app.core.security import CurrentPrincipal
from app.modules.apps.dependencies import AppServiceDep
from app.modules.apps.schemas import AppTargetCreate, AppTargetOut, AppTargetUpdate, AppTestOut, AppTestRequest
from app.modules.projects.dependencies import ProjectScope

router = APIRouter(prefix="/projects/{project_id}/apps", tags=["apps"], dependencies=[Depends(require_feature(APPS))])


@router.post("", status_code=status.HTTP_201_CREATED)
async def add_app(
    body: AppTargetCreate, project: ProjectScope, principal: CurrentPrincipal, service: AppServiceDep
) -> AppTargetOut:
    return await service.create(project, principal, body)


@router.get("")
async def list_apps(project: ProjectScope, service: AppServiceDep) -> list[AppTargetOut]:
    return await service.list(project.id)


@router.get("/{app_id}")
async def get_app(app_id: uuid.UUID, project: ProjectScope, service: AppServiceDep) -> AppTargetOut:
    return await service.get(project.id, app_id)


@router.patch("/{app_id}")
async def change_app(
    app_id: uuid.UUID, body: AppTargetUpdate, project: ProjectScope, service: AppServiceDep
) -> AppTargetOut:
    return await service.update(project.id, app_id, body)


@router.delete("/{app_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_app(app_id: uuid.UUID, project: ProjectScope, service: AppServiceDep) -> None:
    await service.delete(project.id, app_id)


@router.post("/{app_id}/test")
async def try_app(app_id: uuid.UUID, body: AppTestRequest, project: ProjectScope, service: AppServiceDep) -> AppTestOut:
    return await service.test(project.id, app_id, body.inputs)
