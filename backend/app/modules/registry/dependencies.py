"""FastAPI wiring for the registry service."""

from typing import Annotated

from fastapi import Depends

from app.core.container import ContainerDep
from app.core.database import SessionDep
from app.modules.registry.service import RegistryService


def get_registry_service(session: SessionDep, container: ContainerDep) -> RegistryService:
    return RegistryService(session, container)


RegistryServiceDep = Annotated[RegistryService, Depends(get_registry_service)]
