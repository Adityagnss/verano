"""
Logbook HTTP routes (read-only): the filter options, the answers table (paged, sorted,
filtered), one answer in full, the analysis numbers, a CSV of the filtered answers, and the
raw model calls with their detail.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import Response

from app.modules.logbook.dependencies import LogbookDep
from app.modules.logbook.schemas import (
    AnalysisOut,
    AnswerDetail,
    AnswerFilters,
    AnswerPage,
    AnswerQuery,
    CallDetail,
    CallPage,
    CallQuery,
    LogOptions,
)
from app.modules.projects.dependencies import ProjectScope

router = APIRouter(prefix="/projects/{project_id}/logbook", tags=["logbook"])
Filters = Annotated[AnswerFilters, Query()]
AnswerParams = Annotated[AnswerQuery, Query()]
CallParams = Annotated[CallQuery, Query()]


@router.get("/options")
async def options(project: ProjectScope, service: LogbookDep) -> LogOptions:
    return await service.options(project.id)


@router.get("/answers")
async def answers(project: ProjectScope, service: LogbookDep, query: AnswerParams) -> AnswerPage:
    return await service.answers(project.id, query, query.sort, query.order, query.offset, query.limit)


@router.get("/answers.csv")
async def answers_csv(project: ProjectScope, service: LogbookDep, query: AnswerParams) -> Response:
    body = await service.export_csv(project.id, query, query.sort, query.order)
    return Response(
        body, media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="verano-logbook.csv"'}
    )


@router.get("/answers/{experiment_id}/{run_id}")
async def answer(
    experiment_id: uuid.UUID, run_id: uuid.UUID, project: ProjectScope, service: LogbookDep
) -> AnswerDetail:
    return await service.answer(project.id, experiment_id, run_id)


@router.get("/analysis")
async def analysis(project: ProjectScope, service: LogbookDep, filters: Filters) -> AnalysisOut:
    return await service.analysis(project.id, filters)


@router.get("/calls")
async def calls(project: ProjectScope, service: LogbookDep, query: CallParams) -> CallPage:
    return await service.calls(project.id, query, query.offset, query.limit)


@router.get("/calls/{call_id}")
async def call(call_id: uuid.UUID, project: ProjectScope, service: LogbookDep) -> CallDetail:
    return await service.call(project.id, call_id)
