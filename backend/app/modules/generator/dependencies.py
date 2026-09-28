"""FastAPI wiring for the Eval Generator service."""

from typing import Annotated

from fastapi import Depends

from app.core.container import ContainerDep
from app.core.database import SessionDep
from app.modules.generator.service import GeneratorService


def get_generator_service(session: SessionDep, container: ContainerDep) -> GeneratorService:
    return GeneratorService.from_container(session, container)


GeneratorServiceDep = Annotated[GeneratorService, Depends(get_generator_service)]
