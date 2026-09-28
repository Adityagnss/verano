"""
Results HTTP routes: the per-model tradeoff table, the case view (all outputs side by
side, optionally only cases with a failure), CSV export, and rescoring.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status
from fastapi.responses import Response

from app.modules.evaluation.dependencies import ResultsServiceDep
from app.modules.evaluation.schemas import CaseResultOut, RescoreRequest, ResultsOut
from app.modules.projects.dependencies import ProjectScope

router = APIRouter(prefix="/projects/{project_id}/experiments/{experiment_id}", tags=["results"])
RunQuery = Annotated[uuid.UUID | None, Query()]


@router.get("/results")
async def get_results(
    experiment_id: uuid.UUID, project: ProjectScope, service: ResultsServiceDep, evaluation_run_id: RunQuery = None
) -> ResultsOut:
    return await service.results(project.id, experiment_id, evaluation_run_id)


@router.get("/cases")
async def get_cases(
    experiment_id: uuid.UUID,
    project: ProjectScope,
    service: ResultsServiceDep,
    evaluation_run_id: RunQuery = None,
    failed_only: Annotated[bool, Query()] = False,
) -> list[CaseResultOut]:
    return await service.cases(project.id, experiment_id, evaluation_run_id, failed_only)


@router.get("/export.csv")
async def export_csv(
    experiment_id: uuid.UUID, project: ProjectScope, service: ResultsServiceDep, evaluation_run_id: RunQuery = None
) -> Response:
    content = await service.export_csv(project.id, experiment_id, evaluation_run_id)
    headers = {"Content-Disposition": f'attachment; filename="experiment-{experiment_id}.csv"'}
    return Response(content, media_type="text/csv", headers=headers)


@router.post("/rescore", status_code=status.HTTP_202_ACCEPTED)
async def rescore(
    experiment_id: uuid.UUID, body: RescoreRequest, project: ProjectScope, service: ResultsServiceDep
) -> ResultsOut:
    return await service.rescore(project.id, experiment_id, body)
