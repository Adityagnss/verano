"""
Registry HTTP routes: providers, project credentials and discovered models.

Credential responses carry only the last four characters of a key; the key itself is
accepted once, on creation, and never returned by any route.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.core.pagination import Page, PageDep
from app.core.security import CurrentPrincipal
from app.modules.projects.dependencies import ProjectScope
from app.modules.registry.dependencies import RegistryServiceDep
from app.modules.registry.schemas import (
    CredentialCopy,
    CredentialCreate,
    CredentialOut,
    CredentialUpdate,
    ModelProfileOut,
    ModelSelection,
    ProviderOut,
    SharedCredentialOut,
)

router = APIRouter(tags=["registry"])
PROJECT = "/projects/{project_id}"


@router.get("/providers")
async def list_providers(_: CurrentPrincipal, service: RegistryServiceDep) -> list[ProviderOut]:
    return service.providers()


@router.post(f"{PROJECT}/credentials", status_code=status.HTTP_201_CREATED)
async def add_credential(
    body: CredentialCreate, project: ProjectScope, principal: CurrentPrincipal, service: RegistryServiceDep
) -> CredentialOut:
    return await service.add_credential(project, principal, body)


@router.get(f"{PROJECT}/credentials/in-other-projects")
async def credentials_in_other_projects(
    project: ProjectScope, service: RegistryServiceDep
) -> list[SharedCredentialOut]:
    """Keys already added in this organization's other projects."""
    return await service.shared_credentials(project)


@router.post(f"{PROJECT}/credentials/copy", status_code=status.HTTP_201_CREATED)
async def copy_credential(
    body: CredentialCopy, project: ProjectScope, principal: CurrentPrincipal, service: RegistryServiceDep
) -> CredentialOut:
    """Use a key from another project here, without typing it again."""
    return await service.copy_credential(project, principal, body.credential_id)


@router.get(f"{PROJECT}/credentials")
async def list_credentials(project: ProjectScope, service: RegistryServiceDep) -> list[CredentialOut]:
    return await service.list_credentials(project)


@router.patch(f"{PROJECT}/credentials/{{credential_id}}")
async def update_credential(
    credential_id: uuid.UUID,
    body: CredentialUpdate,
    project: ProjectScope,
    principal: CurrentPrincipal,
    service: RegistryServiceDep,
) -> CredentialOut:
    return await service.update_credential(project, credential_id, body, principal)


@router.delete(f"{PROJECT}/credentials/{{credential_id}}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_credential(
    credential_id: uuid.UUID, project: ProjectScope, principal: CurrentPrincipal, service: RegistryServiceDep
) -> None:
    await service.delete_credential(project, credential_id, principal)


@router.post(f"{PROJECT}/credentials/{{credential_id}}/validate")
async def validate_credential(
    credential_id: uuid.UUID, project: ProjectScope, service: RegistryServiceDep
) -> CredentialOut:
    return await service.validate_credential(project, credential_id)


@router.post(f"{PROJECT}/credentials/{{credential_id}}/discover")
async def discover_models(
    credential_id: uuid.UUID, project: ProjectScope, service: RegistryServiceDep
) -> CredentialOut:
    return await service.refresh_models(project, credential_id)


@router.get(f"{PROJECT}/models")
async def list_models(
    project: ProjectScope,
    service: RegistryServiceDep,
    page: PageDep,
    selected: Annotated[bool, Query()] = False,
    credential_id: Annotated[uuid.UUID | None, Query()] = None,
) -> Page[ModelProfileOut]:
    return await service.list_models(project, page, selected, credential_id)


@router.put(f"{PROJECT}/models/selection", status_code=status.HTTP_204_NO_CONTENT)
async def select_models(body: ModelSelection, project: ProjectScope, service: RegistryServiceDep) -> None:
    await service.select_models(project, body)
