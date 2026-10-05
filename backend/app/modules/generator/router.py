"""
Eval Generator HTTP routes: the generator-model suggestion, drafting and confirming the
Task Spec, starting generation (or "Use only my golden set"), regenerating one category,
the live progress stream, and the dataset version's evaluator set (view and edit).
"""

import uuid

from fastapi import APIRouter, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.events import sse_response
from app.core.security import CurrentPrincipal
from app.modules.datasets.schemas import DatasetVersionOut
from app.modules.evaluation.schemas import EvaluatorSetUpdate, EvaluatorSetVersionOut
from app.modules.generator.dependencies import GeneratorServiceDep
from app.modules.generator.schemas import (
    CaseCategory,
    GenerationEstimate,
    GenerationRequest,
    GeneratorSuggestion,
    TaskSpecDraftRequest,
    TaskSpecOut,
    TaskSpecProvide,
    TaskSpecUpdate,
)
from app.modules.projects.dependencies import ProjectScope

router = APIRouter(prefix="/projects/{project_id}", tags=["generator"])
VERSION = "/dataset-versions/{version_id}"


class RegenerateRequest(BaseModel):
    category: CaseCategory


@router.get("/generator/suggestion")
async def suggest_generator(project: ProjectScope, service: GeneratorServiceDep) -> GeneratorSuggestion:
    return await service.suggestion(project)


@router.post("/task-specs", status_code=status.HTTP_201_CREATED)
async def draft_task_spec(
    body: TaskSpecDraftRequest, project: ProjectScope, service: GeneratorServiceDep
) -> TaskSpecOut:
    return await service.draft_spec(project, body)


@router.put("/prompt-versions/{version_id}/task-spec")
async def provide_task_spec(
    version_id: uuid.UUID, body: TaskSpecProvide, project: ProjectScope, service: GeneratorServiceDep
) -> TaskSpecOut:
    return await service.provide_spec(project, version_id, body)


@router.get("/task-specs/{spec_id}")
async def get_task_spec(spec_id: uuid.UUID, project: ProjectScope, service: GeneratorServiceDep) -> TaskSpecOut:
    return await service.get_spec(project, spec_id)


@router.put("/task-specs/{spec_id}")
async def confirm_task_spec(
    spec_id: uuid.UUID, body: TaskSpecUpdate, project: ProjectScope, service: GeneratorServiceDep
) -> TaskSpecOut:
    return await service.confirm_spec(project, spec_id, body.spec)


@router.post("/generations/estimate")
async def estimate_generation(
    body: GenerationRequest, project: ProjectScope, service: GeneratorServiceDep
) -> GenerationEstimate:
    return await service.estimate(project, body)


@router.post("/generations", status_code=status.HTTP_202_ACCEPTED)
async def start_generation(
    body: GenerationRequest, project: ProjectScope, service: GeneratorServiceDep
) -> DatasetVersionOut:
    return await service.start(project, body)


@router.post(f"{VERSION}/regenerate", status_code=status.HTTP_202_ACCEPTED)
async def regenerate_category(
    version_id: uuid.UUID, body: RegenerateRequest, project: ProjectScope, service: GeneratorServiceDep
) -> DatasetVersionOut:
    return await service.regenerate(project, version_id, body.category)


@router.post(f"{VERSION}/generation/cancel")
async def cancel_generation(
    version_id: uuid.UUID, project: ProjectScope, service: GeneratorServiceDep
) -> DatasetVersionOut:
    return await service.cancel(project, version_id)


@router.get(f"{VERSION}/generation/events")
async def generation_events(
    version_id: uuid.UUID, project: ProjectScope, service: GeneratorServiceDep
) -> StreamingResponse:
    return sse_response(await service.events(project, version_id))


@router.get(f"{VERSION}/evaluators")
async def get_evaluators(
    version_id: uuid.UUID, project: ProjectScope, service: GeneratorServiceDep
) -> EvaluatorSetVersionOut:
    return await service.evaluators(project, version_id)


@router.put(f"{VERSION}/evaluators")
async def edit_evaluators(
    version_id: uuid.UUID,
    body: EvaluatorSetUpdate,
    project: ProjectScope,
    principal: CurrentPrincipal,
    service: GeneratorServiceDep,
) -> EvaluatorSetVersionOut:
    return await service.edit_evaluators(project, version_id, body, principal)
