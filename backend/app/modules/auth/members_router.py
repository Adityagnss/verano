"""
Workspace people routes: the member list, role changes, removal, and invites (list, create, issue again, withdraw).

The workspace in the path is checked against the caller's membership, and the minimum role for each route comes
from the permission table, before these handlers run. Role changes add the rule a table cannot hold: an admin
can't give or take away owner or admin, and the last owner can't be removed.
"""

import uuid

from fastapi import APIRouter, status

from app.core.security import CurrentPrincipal
from app.modules.auth.dependencies import AuthServiceDep
from app.modules.auth.schemas import InviteCreate, InviteIssued, InviteOut, MemberOut, RoleChange

router = APIRouter(prefix="/organizations/{organization_id}", tags=["members"])


@router.get("/members")
async def list_members(organization_id: uuid.UUID, auth: AuthServiceDep) -> list[MemberOut]:
    return await auth.members.members(organization_id)


@router.patch("/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def change_role(
    organization_id: uuid.UUID, user_id: uuid.UUID, body: RoleChange, principal: CurrentPrincipal, auth: AuthServiceDep
) -> None:
    await auth.members.change_role(principal, organization_id, user_id, body.role)


@router.delete("/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    organization_id: uuid.UUID, user_id: uuid.UUID, principal: CurrentPrincipal, auth: AuthServiceDep
) -> None:
    await auth.members.remove_member(principal, organization_id, user_id)


@router.get("/invites")
async def list_invites(organization_id: uuid.UUID, auth: AuthServiceDep) -> list[InviteOut]:
    return await auth.members.invites(organization_id)


@router.post("/invites", status_code=status.HTTP_201_CREATED)
async def create_invite(
    organization_id: uuid.UUID, body: InviteCreate, principal: CurrentPrincipal, auth: AuthServiceDep
) -> InviteIssued:
    return await auth.members.create_invite(principal, organization_id, body)


@router.post("/invites/{invite_id}/reissue", status_code=status.HTTP_201_CREATED)
async def reissue_invite(
    organization_id: uuid.UUID, invite_id: uuid.UUID, principal: CurrentPrincipal, auth: AuthServiceDep
) -> InviteIssued:
    return await auth.members.reissue_invite(principal, organization_id, invite_id)


@router.delete("/invites/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_invite(
    organization_id: uuid.UUID, invite_id: uuid.UUID, principal: CurrentPrincipal, auth: AuthServiceDep
) -> None:
    await auth.members.revoke_invite(principal, organization_id, invite_id)
