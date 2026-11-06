"""FastAPI wiring for results."""

from typing import Annotated

from fastapi import Depends

from app.core.container import ContainerDep
from app.core.database import SessionDep
from app.modules.auth.dependencies import AuthServiceDep
from app.modules.evaluation.evidence import EvidenceService
from app.modules.evaluation.labels import LabelService
from app.modules.evaluation.results import ResultsService
from app.modules.evaluation.review import ReviewService
from app.modules.evaluation.rubric import RubricService
from app.modules.evaluation.scoring import ScoringService


def get_results_service(session: SessionDep, container: ContainerDep) -> ResultsService:
    return ResultsService.from_container(session, container)


ResultsServiceDep = Annotated[ResultsService, Depends(get_results_service)]


def get_scoring_service(session: SessionDep, container: ContainerDep) -> ScoringService:
    return ScoringService(session, container)


ScoringServiceDep = Annotated[ScoringService, Depends(get_scoring_service)]


def get_label_service(session: SessionDep, container: ContainerDep) -> LabelService:
    return LabelService(session, container.settings)


LabelServiceDep = Annotated[LabelService, Depends(get_label_service)]


def get_evidence_service(session: SessionDep, container: ContainerDep) -> EvidenceService:
    return EvidenceService(session, container.settings)


EvidenceServiceDep = Annotated[EvidenceService, Depends(get_evidence_service)]


def get_review_service(session: SessionDep, container: ContainerDep, auth: AuthServiceDep) -> ReviewService:
    return ReviewService(session, container.settings, auth)


ReviewServiceDep = Annotated[ReviewService, Depends(get_review_service)]


def get_rubric_service(session: SessionDep, container: ContainerDep) -> RubricService:
    return RubricService(session, container)


RubricServiceDep = Annotated[RubricService, Depends(get_rubric_service)]
