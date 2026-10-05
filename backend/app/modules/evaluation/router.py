"""
Results HTTP routes: the per-model tradeoff table, the case view (all outputs side by
side, optionally only cases with a failure), CSV export, and rescoring.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status
from fastapi.responses import Response

from app.core.security import CurrentPrincipal
from app.modules.evaluation.dependencies import ResultsServiceDep, ScoringServiceDep
from app.modules.evaluation.schemas import (
    CaseResultOut,
    EvaluatorSetVersionOut,
    JudgeCallOut,
    JudgeSuggestion,
    ReplicationOut,
    RescoreEstimate,
    RescoreRequest,
    ResultsOut,
    TryJudgeEstimate,
    TryJudgeOut,
    TryJudgeRequest,
)
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


@router.get("/replication")
async def get_replication(
    experiment_id: uuid.UUID,
    against: Annotated[uuid.UUID, Query()],
    project: ProjectScope,
    service: ResultsServiceDep,
) -> ReplicationOut:
    return await service.replication(project.id, experiment_id, against)


@router.get("/export.csv")
async def export_csv(
    experiment_id: uuid.UUID, project: ProjectScope, service: ResultsServiceDep, evaluation_run_id: RunQuery = None
) -> Response:
    content = await service.export_csv(project.id, experiment_id, evaluation_run_id)
    headers = {"Content-Disposition": f'attachment; filename="experiment-{experiment_id}.csv"'}
    return Response(content, media_type="text/csv", headers=headers)


@router.post("/rescore", status_code=status.HTTP_202_ACCEPTED)
async def rescore(
    experiment_id: uuid.UUID,
    body: RescoreRequest,
    project: ProjectScope,
    principal: CurrentPrincipal,
    service: ResultsServiceDep,
) -> ResultsOut:
    return await service.rescore(project, principal, experiment_id, body)


@router.post("/rescore/estimate")
async def rescore_estimate(
    experiment_id: uuid.UUID, body: RescoreRequest, project: ProjectScope, service: ResultsServiceDep
) -> RescoreEstimate:
    return await service.rescore_estimate(project, experiment_id, body)


@router.get("/answers/{test_case_run_id}/judge-calls")
async def get_judge_calls(
    experiment_id: uuid.UUID, test_case_run_id: uuid.UUID, project: ProjectScope, service: ResultsServiceDep
) -> list[JudgeCallOut]:
    return await service.judge_calls(project.id, experiment_id, test_case_run_id)


@router.post("/judge/try/estimate")
async def try_judge_estimate(
    experiment_id: uuid.UUID, body: TryJudgeRequest, project: ProjectScope, scoring: ScoringServiceDep
) -> TryJudgeEstimate:
    return await scoring.try_estimate(project.id, experiment_id, body)


@router.post("/judge/try")
async def try_judge(
    experiment_id: uuid.UUID, body: TryJudgeRequest, project: ProjectScope, scoring: ScoringServiceDep
) -> TryJudgeOut:
    return await scoring.try_judge(project.id, experiment_id, body)


project_router = APIRouter(prefix="/projects/{project_id}", tags=["evaluators"])


@project_router.get("/evaluator-set-versions/{version_id}")
async def get_evaluator_version(
    version_id: uuid.UUID, project: ProjectScope, service: ResultsServiceDep
) -> EvaluatorSetVersionOut:
    return await service.evaluator_version(project.id, version_id)


@project_router.get("/judge/suggestion")
async def suggest_judge_model(project: ProjectScope, service: ResultsServiceDep) -> JudgeSuggestion:
    return await service.judge_suggestion(project)
