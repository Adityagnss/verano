"""FastAPI wiring for the workspace key store and guardrails."""

from typing import Annotated

from fastapi import Depends

from app.core.container import ContainerDep
from app.core.database import SessionDep
from app.modules.organizations.service import OrganizationService
from app.modules.registry.dependencies import RegistryServiceDep


def get_organization_service(
    session: SessionDep, container: ContainerDep, registry: RegistryServiceDep
) -> OrganizationService:
    return OrganizationService(session, container, registry)


OrganizationServiceDep = Annotated[OrganizationService, Depends(get_organization_service)]
