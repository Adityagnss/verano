"""FastAPI wiring for Improve."""

from typing import Annotated

from fastapi import Depends

from app.core.container import ContainerDep
from app.core.database import SessionDep
from app.modules.assistant.service import ImprovementService


def get_improvement_service(session: SessionDep, container: ContainerDep) -> ImprovementService:
    return ImprovementService(session, container)


ImprovementServiceDep = Annotated[ImprovementService, Depends(get_improvement_service)]
