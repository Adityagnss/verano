"""
Routes for results computed outside Verano. Sending one needs a token that may write (a read-only token is
refused by the permission rules); reading needs only read access. Nothing here starts a run or calls a model.
"""

import uuid

from fastapi import APIRouter, status
from sqlalchemy import select

from app.core.database import SessionDep
from app.core.errors import NotFound
from app.core.pagination import Page, PageDep, keyset, to_page
from app.core.security import CurrentPrincipal
from app.modules.external_results.models import ExternalRun
from app.modules.external_results.schemas import ExternalCase, ExternalRunCreate, ExternalRunOut, ExternalRunSummary
from app.modules.projects.dependencies import ProjectScope

router = APIRouter(prefix="/projects/{project_id}/external-results", tags=["external results"])
NOT_FOUND = "This result doesn't exist in this project."


def _summary(row: ExternalRun) -> ExternalRunSummary:
    return ExternalRunSummary.model_validate({name: getattr(row, name) for name in ExternalRunSummary.model_fields})


@router.post("", status_code=status.HTTP_201_CREATED)
async def send_results(
    body: ExternalRunCreate, project: ProjectScope, principal: CurrentPrincipal, session: SessionDep
) -> ExternalRunOut:
    passed = sum(1 for case in body.cases if case.passed)
    row = ExternalRun(
        project_id=project.id,
        source=body.source,
        name=body.name,
        passed=passed,
        failed=len(body.cases) - passed,
        cases=[case.model_dump() for case in body.cases],
        details=body.details,
        created_by=principal.user_id,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return ExternalRunOut(**_summary(row).model_dump(), cases=body.cases)


@router.get("")
async def list_results(project: ProjectScope, session: SessionDep, page: PageDep) -> Page[ExternalRunSummary]:
    query = keyset(select(ExternalRun).where(ExternalRun.project_id == project.id), ExternalRun.id, page)
    rows = (await session.scalars(query)).all()
    return to_page([_summary(row) for row in rows], page, lambda item: item.id)


@router.get("/{result_id}")
async def get_result(result_id: uuid.UUID, project: ProjectScope, session: SessionDep) -> ExternalRunOut:
    row = await session.scalar(
        select(ExternalRun).where(ExternalRun.id == result_id, ExternalRun.project_id == project.id)
    )
    if row is None:
        raise NotFound(NOT_FOUND)
    return ExternalRunOut(**_summary(row).model_dump(), cases=[ExternalCase(**case) for case in row.cases])
