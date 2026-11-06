"""
Workspace routes: the shared key store and the Guardrails settings (monthly spending limit).

The workspace in the path is checked against the caller's membership and role by the permission table before
these handlers run: members can see the keys and the limit, admins and owners change them. A key is never
returned, only its last four characters.
"""

import uuid

from fastapi import APIRouter, status

from app.core.security import CurrentPrincipal
from app.modules.organizations.dependencies import OrganizationServiceDep
from app.modules.organizations.schemas import (
    GuardrailsOut,
    GuardrailsUpdate,
    OrgKeyAttach,
    OrgKeyCreate,
    OrgKeyFromCredential,
    OrgKeyOut,
    OrgKeyRotate,
    OrgKeyUpdate,
)

router = APIRouter(prefix="/organizations/{organization_id}", tags=["organizations"])


@router.get("/keys")
async def list_keys(organization_id: uuid.UUID, service: OrganizationServiceDep) -> list[OrgKeyOut]:
    return await service.keys(organization_id)


@router.post("/keys", status_code=status.HTTP_201_CREATED)
async def create_key(
    organization_id: uuid.UUID, body: OrgKeyCreate, principal: CurrentPrincipal, service: OrganizationServiceDep
) -> OrgKeyOut:
    return await service.create_key(principal, organization_id, body)


@router.post("/keys/from-credential", status_code=status.HTTP_201_CREATED)
async def move_project_key(
    organization_id: uuid.UUID,
    body: OrgKeyFromCredential,
    principal: CurrentPrincipal,
    service: OrganizationServiceDep,
) -> OrgKeyOut:
    """Move a key a project already has to the workspace store; nothing stops working."""
    return await service.promote(principal, organization_id, body.project_id, body.credential_id)


@router.patch("/keys/{key_id}")
async def update_key(
    organization_id: uuid.UUID,
    key_id: uuid.UUID,
    body: OrgKeyUpdate,
    principal: CurrentPrincipal,
    service: OrganizationServiceDep,
) -> OrgKeyOut:
    return await service.update_key(principal, organization_id, key_id, body)


@router.post("/keys/{key_id}/rotate")
async def rotate_key(
    organization_id: uuid.UUID,
    key_id: uuid.UUID,
    body: OrgKeyRotate,
    principal: CurrentPrincipal,
    service: OrganizationServiceDep,
) -> OrgKeyOut:
    """Replace the key everywhere it is used; the old key is used nowhere afterwards."""
    return await service.rotate_key(principal, organization_id, key_id, body.api_key.get_secret_value())


@router.delete("/keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_key(
    organization_id: uuid.UUID, key_id: uuid.UUID, principal: CurrentPrincipal, service: OrganizationServiceDep
) -> None:
    await service.delete_key(principal, organization_id, key_id)


@router.post("/keys/{key_id}/projects", status_code=status.HTTP_201_CREATED)
async def use_key_in_project(
    organization_id: uuid.UUID,
    key_id: uuid.UUID,
    body: OrgKeyAttach,
    principal: CurrentPrincipal,
    service: OrganizationServiceDep,
) -> OrgKeyOut:
    return await service.attach(principal, organization_id, key_id, body.project_id)


@router.delete("/keys/{key_id}/projects/{project_id}")
async def stop_using_key_in_project(
    organization_id: uuid.UUID,
    key_id: uuid.UUID,
    project_id: uuid.UUID,
    principal: CurrentPrincipal,
    service: OrganizationServiceDep,
) -> OrgKeyOut:
    return await service.detach(principal, organization_id, key_id, project_id)


@router.get("/guardrails")
async def get_guardrails(organization_id: uuid.UUID, service: OrganizationServiceDep) -> GuardrailsOut:
    return await service.guardrails(organization_id)


@router.put("/guardrails")
async def set_guardrails(
    organization_id: uuid.UUID, body: GuardrailsUpdate, principal: CurrentPrincipal, service: OrganizationServiceDep
) -> GuardrailsOut:
    return await service.set_guardrails(principal, organization_id, body)
