"""
Results HTTP routes: the per-model tradeoff table, the case view (all outputs side by
side, optionally only cases with a failure), CSV export, and rescoring.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status
from fastapi.responses import Response

from app.core.security import CurrentPrincipal
from app.modules.evaluation.dependencies import (
    EvidenceServiceDep,
    LabelServiceDep,
    ResultsServiceDep,
    ScoringServiceDep,
)
from app.modules.evaluation.gallery import NOT_MEASURED, as_config, gallery
from app.modules.evaluation.schemas import (
    AgreementOut,
    CaseResultOut,
    EvaluatorSetVersionOut,
    EvidenceOut,
    GalleryJudgeOut,
    JudgeCallOut,
    JudgeSuggestion,
    LabelIn,
    LabelOut,
    ReplicationOut,
    RescoreEstimate,
    RescoreRequest,
    ResultsOut,
    TryJudgeEstimate,
    TryJudgeOut,
    TryJudgeRequest,
    VersionComparisonOut,
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
    principal: CurrentPrincipal,
    evaluation_run_id: RunQuery = None,
    failed_only: Annotated[bool, Query()] = False,
    blind: Annotated[bool, Query()] = False,
) -> list[CaseResultOut]:
    return await service.cases(project.id, experiment_id, evaluation_run_id, failed_only, principal.user_id, blind)


@router.get("/compare")
async def compare_experiments(
    experiment_id: uuid.UUID,
    against: Annotated[uuid.UUID, Query()],
    project: ProjectScope,
    service: ResultsServiceDep,
) -> VersionComparisonOut:
    return await service.compare_versions(project.id, experiment_id, against)


@router.put("/answers/{test_case_run_id}/label")
async def put_label(
    experiment_id: uuid.UUID,
    test_case_run_id: uuid.UUID,
    body: LabelIn,
    project: ProjectScope,
    principal: CurrentPrincipal,
    labels: LabelServiceDep,
) -> LabelOut:
    return await labels.set_label(project.id, experiment_id, principal, test_case_run_id, body)


@router.delete("/answers/{test_case_run_id}/label", status_code=status.HTTP_204_NO_CONTENT)
async def delete_label(
    experiment_id: uuid.UUID,
    test_case_run_id: uuid.UUID,
    project: ProjectScope,
    principal: CurrentPrincipal,
    labels: LabelServiceDep,
) -> None:
    await labels.remove_label(project.id, experiment_id, principal, test_case_run_id)


@router.get("/answers/{test_case_run_id}/evidence")
async def get_evidence(
    experiment_id: uuid.UUID,
    test_case_run_id: uuid.UUID,
    project: ProjectScope,
    evidence: EvidenceServiceDep,
    evaluation_run_id: RunQuery = None,
) -> EvidenceOut:
    return await evidence.evidence(project.id, experiment_id, test_case_run_id, evaluation_run_id)


@router.get("/labels")
async def get_labels(experiment_id: uuid.UUID, project: ProjectScope, labels: LabelServiceDep) -> list[LabelOut]:
    return await labels.labels(project.id, experiment_id)


@router.get("/agreement")
async def get_agreement(
    experiment_id: uuid.UUID, project: ProjectScope, labels: LabelServiceDep, evaluation_run_id: RunQuery = None
) -> list[AgreementOut]:
    return await labels.agreement(project.id, experiment_id, evaluation_run_id)


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


@project_router.get("/judge-gallery")
async def get_judge_gallery(project: ProjectScope) -> list[GalleryJudgeOut]:
    """The ready-made judges that can be added to this project's checks, with what each cannot tell and how
    often it agrees with people (or that this was not measured yet)."""
    return [
        GalleryJudgeOut(
            id=name,
            title=entry.title,
            description=entry.description,
            requires=entry.requires,
            threshold=entry.threshold,
            criteria=entry.criteria,
            limits=entry.limits,
            agreement=entry.agreement.model_dump() if entry.agreement else None,
            agreement_note=None if entry.agreement else NOT_MEASURED,
            config=as_config(name, entry),
        )
        for name, entry in gallery().judges.items()
    ]
