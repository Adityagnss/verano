"""FastAPI wiring for the experiment service."""

from typing import Annotated

from fastapi import Depends

from app.core.container import ContainerDep
from app.core.database import SessionDep
from app.modules.engine.service import ExperimentService


def get_experiment_service(session: SessionDep, container: ContainerDep) -> ExperimentService:
    return ExperimentService.from_container(session, container)


ExperimentServiceDep = Annotated[ExperimentService, Depends(get_experiment_service)]
