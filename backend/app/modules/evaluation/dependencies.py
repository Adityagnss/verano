"""FastAPI wiring for results."""

from typing import Annotated

from fastapi import Depends

from app.core.container import ContainerDep
from app.core.database import SessionDep
from app.modules.evaluation.results import ResultsService
from app.modules.evaluation.scoring import ScoringService


def get_results_service(session: SessionDep, container: ContainerDep) -> ResultsService:
    return ResultsService.from_container(session, container)


ResultsServiceDep = Annotated[ResultsService, Depends(get_results_service)]


def get_scoring_service(session: SessionDep, container: ContainerDep) -> ScoringService:
    return ScoringService(session, container)


ScoringServiceDep = Annotated[ScoringService, Depends(get_scoring_service)]
