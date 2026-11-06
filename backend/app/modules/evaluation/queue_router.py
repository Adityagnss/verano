"""
Review queue HTTP routes (ADR 0038): give answers to people to label, a person's queue and progress, and settling
disagreements between labels. Labelling itself uses the existing label route. Switched off with the
`review_queue` feature.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.features import REVIEW_QUEUE, require_feature
from app.core.pagination import PageDep
from app.core.security import CurrentPrincipal
from app.modules.evaluation.dependencies import ReviewServiceDep
from app.modules.evaluation.review_schemas import (
    AssignOut,
    AssignRequest,
    DisputeOut,
    ProgressOut,
    QueueOut,
    QueueStatus,
    ResolutionOut,
    ResolveRequest,
    ReviewMemberOut,
)
from app.modules.projects.dependencies import ProjectScope

router = APIRouter(
    prefix="/projects/{project_id}/review-queue",
    tags=["review queue"],
    dependencies=[Depends(require_feature(REVIEW_QUEUE))],
)
ExperimentQuery = Annotated[uuid.UUID | None, Query()]


@router.get("/members")
async def get_members(project: ProjectScope, service: ReviewServiceDep) -> list[ReviewMemberOut]:
    """The people who can be given answers to label."""
    return await service.members(project)


@router.post("/assignments", status_code=status.HTTP_201_CREATED)
async def assign(
    body: AssignRequest, project: ProjectScope, principal: CurrentPrincipal, service: ReviewServiceDep
) -> AssignOut:
    return await service.assign(project, principal, body)


@router.delete("/assignments/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unassign(
    assignment_id: uuid.UUID, project: ProjectScope, principal: CurrentPrincipal, service: ReviewServiceDep
) -> None:
    await service.unassign(project, principal, assignment_id)


@router.get("/mine")
async def my_queue(
    project: ProjectScope,
    principal: CurrentPrincipal,
    service: ReviewServiceDep,
    page: PageDep,
    status_filter: Annotated[QueueStatus, Query(alias="status")] = QueueStatus.OPEN,
    experiment_id: ExperimentQuery = None,
    blind: Annotated[bool, Query()] = False,
) -> QueueOut:
    """Your queue, in the order answers were given to you. `blind=true` hides every judge field even for
    assignments that were not given blind."""
    return await service.queue(project, principal, status_filter, experiment_id, page, blind)


@router.get("/progress")
async def get_progress(
    project: ProjectScope, service: ReviewServiceDep, experiment_id: ExperimentQuery = None
) -> ProgressOut:
    return await service.progress(project, experiment_id)


@router.get("/disputes")
async def get_disputes(
    project: ProjectScope,
    service: ReviewServiceDep,
    experiment_id: Annotated[uuid.UUID, Query()],
    include_settled: Annotated[bool, Query()] = False,
) -> list[DisputeOut]:
    return await service.disputes(project, experiment_id, include_settled)


@router.put("/disputes/{experiment_id}/{test_case_run_id}/resolution")
async def resolve(
    experiment_id: uuid.UUID,
    test_case_run_id: uuid.UUID,
    body: ResolveRequest,
    project: ProjectScope,
    principal: CurrentPrincipal,
    service: ReviewServiceDep,
) -> ResolutionOut:
    return await service.resolve(project, principal, experiment_id, test_case_run_id, body)


@router.delete("/disputes/{experiment_id}/{test_case_run_id}/resolution", status_code=status.HTTP_204_NO_CONTENT)
async def unresolve(
    experiment_id: uuid.UUID,
    test_case_run_id: uuid.UUID,
    project: ProjectScope,
    principal: CurrentPrincipal,
    service: ReviewServiceDep,
) -> None:
    await service.unresolve(project, principal, experiment_id, test_case_run_id)
