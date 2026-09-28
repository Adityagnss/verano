"""
Review & Approve HTTP routes (DEVELOPMENT.md 2.4): the current dataset version and its
summary, the case table (filter by source, category, review status or split), adding,
editing and deleting cases, bulk-approving drafts, and approving the version.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.core.pagination import Page, PageDep
from app.core.security import CurrentPrincipal
from app.modules.datasets.dependencies import DatasetServiceDep
from app.modules.datasets.schemas import (
    BulkApprove,
    DatasetVersionOut,
    ItemCreate,
    ItemFilter,
    ItemOut,
    ItemUpdate,
)
from app.modules.projects.dependencies import ProjectScope

router = APIRouter(prefix="/projects/{project_id}/dataset-versions", tags=["datasets"])
VERSION = "/{version_id}"
ITEM = "/{version_id}/items/{item_id}"


@router.get("/current")
async def current_version(project: ProjectScope, service: DatasetServiceDep) -> DatasetVersionOut:
    return await service.current(project.id)


@router.get(VERSION)
async def get_version(version_id: uuid.UUID, project: ProjectScope, service: DatasetServiceDep) -> DatasetVersionOut:
    return await service.get_version(project.id, version_id)


@router.get(f"{VERSION}/items")
async def list_items(
    version_id: uuid.UUID,
    project: ProjectScope,
    service: DatasetServiceDep,
    page: PageDep,
    where: Annotated[ItemFilter, Query()],
) -> Page[ItemOut]:
    return await service.list_items(project.id, version_id, where, page)


@router.post(f"{VERSION}/items", status_code=status.HTTP_201_CREATED)
async def add_item(
    version_id: uuid.UUID, body: ItemCreate, project: ProjectScope, service: DatasetServiceDep
) -> ItemOut:
    return await service.add_item(project.id, version_id, body)


@router.patch(ITEM)
async def edit_item(
    version_id: uuid.UUID, item_id: uuid.UUID, body: ItemUpdate, project: ProjectScope, service: DatasetServiceDep
) -> ItemOut:
    return await service.edit_item(project.id, version_id, item_id, body)


@router.delete(ITEM, status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    version_id: uuid.UUID, item_id: uuid.UUID, project: ProjectScope, service: DatasetServiceDep
) -> None:
    await service.delete_item(project.id, version_id, item_id)


@router.post(f"{VERSION}/approve-drafts")
async def approve_drafts(
    version_id: uuid.UUID, body: BulkApprove, project: ProjectScope, service: DatasetServiceDep
) -> DatasetVersionOut:
    return await service.approve_drafts(project.id, version_id, body)


@router.post(f"{VERSION}/approve")
async def approve_version(
    version_id: uuid.UUID, project: ProjectScope, principal: CurrentPrincipal, service: DatasetServiceDep
) -> DatasetVersionOut:
    return await service.approve(project.id, version_id, principal)
