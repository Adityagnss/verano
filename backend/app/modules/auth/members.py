"""
Members, invites and email verification of a workspace (organization).

Who may do what is decided by the permission table before any of this runs (viewers read the member list;
admins and owners manage it). What is checked here is the part a role table cannot say: an admin may not hand out
or take away the owner or admin role, a workspace always keeps one owner, and an invite works only for the email
it was sent to. An invite link carries a random token whose SHA-256 digest is stored; the link is returned once,
when the invite is made or issued again, so an owner can pass it on when email is not set up. Every change is
written to the audit log in the same transaction.
"""

import uuid
from collections.abc import Callable
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError, Conflict, NotFound, PermissionDenied, ValidationFailed
from app.core.mail import Mailer
from app.core.permissions import Role, outranks
from app.core.security import Principal, digest_token, new_refresh_token, utcnow
from app.modules.audit.schemas import AuditAction
from app.modules.audit.service import AuditLog
from app.modules.auth.domain import InviteStatus, invite_status, normalize_email, role_change_problem
from app.modules.auth.models import Invite, User
from app.modules.auth.repository import AuthRepository
from app.modules.auth.schemas import InviteCreate, InviteIssued, InviteOut, InvitePreview, MemberOut

INVITE_INVALID = "This invite link isn't valid. Ask the person who invited you for a new one."
INVITE_NOT_FOUND = "This invite doesn't exist."
INVITE_EXPIRED = "This invite link has expired. Ask the person who invited you to send a new one."
INVITE_REVOKED = "This invite was withdrawn. Ask the person who invited you to send a new one."
INVITE_USED = "This invite was already used."
INVITE_OTHER_EMAIL = "This invite was sent to {email}. Sign in with that email to accept it."
INVITE_NEEDS_VERIFIED = "Verify your email address first (we sent you a link), then open the invite again."
ALREADY_MEMBER = "{email} is already a member of this workspace."
TOO_MANY_INVITES = "This workspace already has {limit} open invites. Withdraw some before sending more."
MEMBER_NOT_FOUND = "This person isn't a member of this workspace."
VERIFY_INVALID = "This verification link isn't valid or has expired. Sign in and ask for a new one."
MAIL_OFF = "Email isn't set up on this server, so verification emails can't be sent."
INVITE_REMOVED_ORG = "This workspace no longer exists."


class InviteUnusable(AppError):
    status_code = 410
    code = "invite_unusable"


class MemberService:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        mailer: Mailer | None = None,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._session = session
        self._repo = AuthRepository(session)
        self._settings = settings
        self._mailer = mailer or Mailer(settings)
        self._audit = AuditLog(session, settings)
        self._clock = clock

    # --- members -----------------------------------------------------------------------------------

    async def members(self, organization_id: uuid.UUID) -> list[MemberOut]:
        return [
            MemberOut(
                user_id=user.id,
                name=user.name,
                email=user.email,
                role=membership.role,
                joined_at=membership.created_at,
                email_verified=user.email_verified,
            )
            for membership, user in await self._repo.members(organization_id)
        ]

    async def change_role(self, actor: Principal, organization_id: uuid.UUID, user_id: uuid.UUID, role: Role) -> None:
        await self._repo.lock_organization(organization_id)
        current = await self._repo.role_in(user_id, organization_id)
        if current is None:
            raise NotFound(MEMBER_NOT_FOUND)
        if current is role:
            return
        actor_role = await self._actor_role(actor, organization_id)
        owners_left = await self._repo.owner_count(organization_id) - (1 if current is Role.OWNER else 0)
        owners_left += 1 if role is Role.OWNER else 0
        problem = role_change_problem(actor_role, current, role, owners_left)
        if problem:
            raise PermissionDenied(problem)
        await self._repo.set_role(organization_id, user_id, role)
        target = await self._repo.user(user_id)
        who = target.email if target else str(user_id)
        await self._audit.record(
            organization_id=organization_id,
            actor_id=actor.user_id,
            action=AuditAction.ROLE_CHANGED,
            summary=f"Changed the role of {who} from {current.value} to {role.value}.",
            target_type="user",
            target_id=user_id,
            details={"from": current.value, "to": role.value},
        )

    async def remove_member(self, actor: Principal, organization_id: uuid.UUID, user_id: uuid.UUID) -> None:
        await self._repo.lock_organization(organization_id)
        current = await self._repo.role_in(user_id, organization_id)
        if current is None:
            raise NotFound(MEMBER_NOT_FOUND)
        organization = await self._repo.organization(organization_id)
        if organization is not None and organization.is_personal:
            raise Conflict("A personal workspace belongs to its owner and can't have its owner removed.")
        actor_role = await self._actor_role(actor, organization_id)
        owners_left = await self._repo.owner_count(organization_id) - (1 if current is Role.OWNER else 0)
        problem = role_change_problem(actor_role, current, None, owners_left)
        if problem:
            raise PermissionDenied(problem)
        await self._repo.remove_membership(organization_id, user_id)
        target = await self._repo.user(user_id)
        await self._audit.record(
            organization_id=organization_id,
            actor_id=actor.user_id,
            action=AuditAction.MEMBER_REMOVED,
            summary=f"Removed {target.email if target else user_id} from the workspace.",
            target_type="user",
            target_id=user_id,
            details={"role": current.value},
        )

    # --- invites -----------------------------------------------------------------------------------

    async def invites(self, organization_id: uuid.UUID) -> list[InviteOut]:
        now = self._clock()
        return [self._invite_out(invite, name, now) for invite, name in await self._repo.invites(organization_id)]

    async def create_invite(self, actor: Principal, organization_id: uuid.UUID, body: InviteCreate) -> InviteIssued:
        now = self._clock()
        email = normalize_email(body.email)
        actor_role = await self._actor_role(actor, organization_id)
        if not outranks(actor_role, body.role):
            raise PermissionDenied(f"Your role can't invite someone as {body.role.value}. Ask an owner.")
        organization = await self._repo.organization(organization_id)
        if organization is None:
            raise NotFound(INVITE_REMOVED_ORG)
        if organization.is_personal:
            raise Conflict("Invites are for shared workspaces. Create or use a shared workspace to invite people.")
        if any(user.email == email for _, user in await self._repo.members(organization_id)):
            raise Conflict(ALREADY_MEMBER.format(email=email))
        if await self._repo.open_invite_count(organization_id, now) >= self._settings.max_open_invites:
            raise Conflict(TOO_MANY_INVITES.format(limit=self._settings.max_open_invites))
        await self._repo.revoke_open_invites_for(organization_id, email, now)
        issued = await self._issue(actor, organization.name, organization_id, email, body.role, now)
        await self._audit.record(
            organization_id=organization_id,
            actor_id=actor.user_id,
            action=AuditAction.INVITE_SENT,
            summary=f"Invited {email} as {body.role.value}.",
            target_type="invite",
            target_id=issued.id,
            details={"email": email, "role": body.role.value, "emailed": issued.emailed},
        )
        return issued

    async def reissue_invite(self, actor: Principal, organization_id: uuid.UUID, invite_id: uuid.UUID) -> InviteIssued:
        now = self._clock()
        old = await self._repo.invite(organization_id, invite_id)
        if old is None:
            raise NotFound(INVITE_NOT_FOUND)
        if old.accepted_at is not None:
            raise Conflict(INVITE_USED)
        actor_role = await self._actor_role(actor, organization_id)
        if not outranks(actor_role, old.role):
            raise PermissionDenied(f"Your role can't invite someone as {old.role.value}. Ask an owner.")
        organization = await self._repo.organization(organization_id)
        if organization is None:
            raise NotFound(INVITE_REMOVED_ORG)
        await self._repo.revoke_open_invites_for(organization_id, old.email, now)
        issued = await self._issue(actor, organization.name, organization_id, old.email, old.role, now)
        await self._audit.record(
            organization_id=organization_id,
            actor_id=actor.user_id,
            action=AuditAction.INVITE_SENT,
            summary=f"Sent a new invite to {old.email} as {old.role.value}.",
            target_type="invite",
            target_id=issued.id,
            details={"email": old.email, "role": old.role.value, "reissued": True},
        )
        return issued

    async def revoke_invite(self, actor: Principal, organization_id: uuid.UUID, invite_id: uuid.UUID) -> None:
        now = self._clock()
        invite = await self._repo.invite(organization_id, invite_id)
        if invite is None:
            raise NotFound(INVITE_NOT_FOUND)
        if invite_status(invite.expires_at, invite.accepted_at, invite.revoked_at, now) is not InviteStatus.OPEN:
            return
        invite.revoked_at = now
        await self._audit.record(
            organization_id=organization_id,
            actor_id=actor.user_id,
            action=AuditAction.INVITE_REVOKED,
            summary=f"Withdrew the invite to {invite.email}.",
            target_type="invite",
            target_id=invite.id,
            details={"email": invite.email},
        )

    async def preview(self, raw_token: str) -> InvitePreview:
        invite = await self._repo.invite_by_token(digest_token(raw_token))
        if invite is None:
            raise NotFound(INVITE_INVALID)
        organization = await self._repo.organization(invite.organization_id)
        status = invite_status(invite.expires_at, invite.accepted_at, invite.revoked_at, self._clock())
        return InvitePreview(
            organization_name=organization.name if organization else "",
            email=invite.email,
            role=invite.role,
            expires_at=invite.expires_at,
            status=status.value,
        )

    async def accept(self, principal: Principal, raw_token: str) -> uuid.UUID:
        """Join the workspace the invite is for. Returns the workspace id."""
        now = self._clock()
        invite = await self._repo.invite_by_token(digest_token(raw_token), for_update=True)
        if invite is None:
            raise NotFound(INVITE_INVALID)
        status = invite_status(invite.expires_at, invite.accepted_at, invite.revoked_at, now)
        if status is InviteStatus.EXPIRED:
            raise InviteUnusable(INVITE_EXPIRED)
        if status is InviteStatus.REVOKED:
            raise InviteUnusable(INVITE_REVOKED)
        if status is InviteStatus.ACCEPTED:
            raise InviteUnusable(INVITE_USED)
        user = await self._repo.user(principal.user_id)
        if user is None:
            raise NotFound("This account no longer exists.")
        if user.email != invite.email:
            raise PermissionDenied(INVITE_OTHER_EMAIL.format(email=invite.email))
        if not user.email_verified:
            if invite.emailed_at is not None:
                await self._repo.mark_verified(user.id, now)  # the link reached this address, so it is theirs
            elif self._mailer.enabled:
                raise PermissionDenied(INVITE_NEEDS_VERIFIED)
        invite.accepted_at = now
        invite.accepted_by = user.id
        if await self._repo.role_in(user.id, invite.organization_id) is None:
            await self._repo.add_membership(invite.organization_id, user.id, invite.role)
            await self._audit.record(
                organization_id=invite.organization_id,
                actor_id=user.id,
                action=AuditAction.INVITE_ACCEPTED,
                summary=f"{user.email} accepted the invite and joined as {invite.role.value}.",
                target_type="user",
                target_id=user.id,
                details={"role": invite.role.value, "invite_id": str(invite.id)},
            )
        return invite.organization_id

    # --- email verification --------------------------------------------------------------------------

    async def send_verification(self, user: User) -> bool:
        """Email a verification link. False when email is not set up or the send failed."""
        if user.email_verified or not self._mailer.enabled:
            return False
        raw = new_refresh_token()
        expires = self._clock() + timedelta(hours=self._settings.email_verification_ttl_hours)
        await self._repo.add_verification(user.id, digest_token(raw), expires)
        link = f"{self._settings.public_url.rstrip('/')}/verify-email?token={raw}"
        body = (
            f"Hello {user.name},\n\nConfirm your email address for Verano by opening this link:\n{link}\n\n"
            f"It works for {self._settings.email_verification_ttl_hours} hours. "
            "If you didn't sign up, ignore this email."
        )
        return await self._mailer.send(user.email, "Confirm your email for Verano", body)

    async def resend_verification(self, principal: Principal) -> bool:
        user = await self._repo.user(principal.user_id)
        if user is None:
            raise NotFound("This account no longer exists.")
        if user.email_verified:
            return True
        if not self._mailer.enabled:
            raise Conflict(MAIL_OFF)
        return await self.send_verification(user)

    async def verify_email(self, raw_token: str) -> None:
        now = self._clock()
        record = await self._repo.verification_for_update(digest_token(raw_token))
        if record is None or record.used_at is not None or record.expires_at <= now:
            raise ValidationFailed(VERIFY_INVALID)
        await self._repo.mark_verified(record.user_id, now)

    # --- helpers -----------------------------------------------------------------------------------

    async def _issue(
        self,
        actor: Principal,
        organization_name: str,
        organization_id: uuid.UUID,
        email: str,
        role: Role,
        now: datetime,
    ) -> InviteIssued:
        raw = new_refresh_token()
        invite = await self._repo.add_invite(
            Invite(
                organization_id=organization_id,
                email=email,
                role=role,
                token_hash=digest_token(raw),
                invited_by=actor.user_id,
                expires_at=now + timedelta(days=self._settings.invite_ttl_days),
            )
        )
        link = f"{self._settings.public_url.rstrip('/')}/invite/{raw}"
        inviter = await self._repo.user(actor.user_id)
        body = (
            f"{inviter.name if inviter else 'Someone'} invited you to join {organization_name} on Verano "
            f"as {role.value}.\n\nOpen this link to accept (sign in or create an account with {email}):\n{link}\n\n"
            f"The link works for {self._settings.invite_ttl_days} days."
        )
        if await self._mailer.send(email, f"You're invited to {organization_name} on Verano", body):
            invite.emailed_at = now
        out = self._invite_out(invite, inviter.name if inviter else None, now)
        return InviteIssued(**out.model_dump(), link=link)

    def _invite_out(self, invite: Invite, inviter_name: str | None, now: datetime) -> InviteOut:
        return InviteOut(
            id=invite.id,
            email=invite.email,
            role=invite.role,
            created_at=invite.created_at,
            expires_at=invite.expires_at,
            status=invite_status(invite.expires_at, invite.accepted_at, invite.revoked_at, now).value,
            emailed=invite.emailed_at is not None,
            invited_by_name=inviter_name,
        )

    async def _actor_role(self, actor: Principal, organization_id: uuid.UUID) -> Role:
        role = await self._repo.role_in(actor.user_id, organization_id)
        if role is None:
            raise NotFound("This workspace doesn't exist or you aren't a member of it.")
        return role
