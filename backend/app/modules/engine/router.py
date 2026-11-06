"""
Experiment HTTP routes: the cost preview, start, list, one experiment with live progress
per model, cancel, and the full record of one call.
"""

import uuid

from fastapi import APIRouter, status
from fastapi.responses import StreamingResponse

from app.core.container import ContainerDep
from app.core.events import sse_response
from app.core.pagination import Page, PageDep
from app.core.security import CurrentPrincipal
from app.modules.engine.dependencies import ExperimentServiceDep
from app.modules.engine.live import stream_experiment
from app.modules.engine.schemas import (
    ExperimentCreate,
    ExperimentEstimate,
    ExperimentOut,
    ResumeRequest,
    TestCaseRunOut,
)
from app.modules.projects.dependencies import ProjectScope

router = APIRouter(prefix="/projects/{project_id}/experiments", tags=["experiments"])
EXPERIMENT = "/{experiment_id}"


@router.post("/estimate")
async def estimate_experiment(
    body: ExperimentCreate, project: ProjectScope, service: ExperimentServiceDep
) -> ExperimentEstimate:
    return await service.estimate(project, body)


@router.post("", status_code=status.HTTP_201_CREATED)
async def start_experiment(
    body: ExperimentCreate, project: ProjectScope, principal: CurrentPrincipal, service: ExperimentServiceDep
) -> ExperimentOut:
    return await service.start(project.id, principal, body)


@router.get("")
async def list_experiments(project: ProjectScope, service: ExperimentServiceDep, page: PageDep) -> Page[ExperimentOut]:
    return await service.list_experiments(project, page)


@router.get(EXPERIMENT)
async def get_experiment(
    experiment_id: uuid.UUID, project: ProjectScope, service: ExperimentServiceDep
) -> ExperimentOut:
    return await service.get(project.id, experiment_id)


@router.post(f"{EXPERIMENT}/cancel")
async def cancel_experiment(
    experiment_id: uuid.UUID, project: ProjectScope, service: ExperimentServiceDep
) -> ExperimentOut:
    return await service.cancel(project, experiment_id)


@router.post(f"{EXPERIMENT}/rerun", status_code=status.HTTP_201_CREATED)
async def rerun_experiment(
    experiment_id: uuid.UUID, project: ProjectScope, principal: CurrentPrincipal, service: ExperimentServiceDep
) -> ExperimentOut:
    return await service.rerun(project, principal, experiment_id)


@router.get(f"{EXPERIMENT}/runs/{{run_id}}")
async def get_run(
    experiment_id: uuid.UUID, run_id: uuid.UUID, project: ProjectScope, service: ExperimentServiceDep
) -> TestCaseRunOut:
    return await service.get_run(project.id, experiment_id, run_id)


@router.post(f"{EXPERIMENT}/pause")
async def pause_experiment(
    experiment_id: uuid.UUID, project: ProjectScope, service: ExperimentServiceDep
) -> ExperimentOut:
    """Stop starting new calls; pending calls stay pending until Resume."""
    return await service.pause_by_user(project, experiment_id)


@router.post(f"{EXPERIMENT}/resume")
async def resume_experiment(
    experiment_id: uuid.UUID, project: ProjectScope, service: ExperimentServiceDep, body: ResumeRequest | None = None
) -> ExperimentOut:
    """Carry on exactly where a paused run stopped (optionally with a higher budget cap). No call is repeated."""
    return await service.resume(project, experiment_id, body.budget_cap if body else None)


@router.post(f"{EXPERIMENT}/retry-failed")
async def retry_failed(experiment_id: uuid.UUID, project: ProjectScope, service: ExperimentServiceDep) -> ExperimentOut:
    """Queue again the calls that failed because the provider was down or slow."""
    return await service.retry_failed(project, experiment_id)


@router.get(f"{EXPERIMENT}/events")
async def experiment_events(
    experiment_id: uuid.UUID, project: ProjectScope, service: ExperimentServiceDep, container: ContainerDep
) -> StreamingResponse:
    """Live progress as Server-Sent Events: one event whenever the run's numbers or state change, until it ends."""
    await service.get(project.id, experiment_id)  # 404 before streaming starts
    return sse_response(stream_experiment(container, project.id, experiment_id))
