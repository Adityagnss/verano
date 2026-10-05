"""
Experiment HTTP routes: the cost preview, start, list, one experiment with live progress
per model, cancel, and the full record of one call.
"""

import uuid

from fastapi import APIRouter, status

from app.core.pagination import Page, PageDep
from app.core.security import CurrentPrincipal
from app.modules.engine.dependencies import ExperimentServiceDep
from app.modules.engine.schemas import ExperimentCreate, ExperimentEstimate, ExperimentOut, TestCaseRunOut
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
