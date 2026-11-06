"""
Auth data access.

All queries on users, organizations, memberships and refresh_tokens. The refresh-token
lookup takes a row lock (`FOR UPDATE`) so two concurrent refreshes with the same token are
serialized: the second one sees `used_at` set and is treated as reuse. When open sign-up is
off, a transaction-scoped advisory lock serializes the "is this the first user?" check.
"""

import uuid
from datetime import datetime

from sqlalchemy import delete, exists, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import (
    ApiToken,
    EmailVerification,
    ExternalIdentity,
    Invite,
    Membership,
    Organization,
    RefreshToken,
    User,
)
from app.modules.auth.schemas import MembershipRole, TokenScope

SIGNUP_LOCK_KEY = 0x7665_7261_6E6F


class AuthRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def user_by_email(self, email: str) -> User | None:
        return await self._session.scalar(select(User).where(User.email == email))

    async def has_users(self) -> bool:
        return bool(await self._session.scalar(select(exists().where(User.id.is_not(None)))))

    async def lock_signups(self) -> None:
        await self._session.execute(select(func.pg_advisory_xact_lock(SIGNUP_LOCK_KEY)))

    async def user(self, user_id: uuid.UUID) -> User | None:
        return await self._session.get(User, user_id)

    async def create_user_with_personal_org(self, email: str, name: str, password_hash: str, org_name: str) -> User:
        user = User(email=email, name=name, password_hash=password_hash)
        org = Organization(name=org_name, is_personal=True)
        self._session.add_all([user, org])
        await self._session.flush()
        self._session.add(Membership(organization_id=org.id, user_id=user.id, role=MembershipRole.OWNER))
        await self._session.flush()
        return user

    async def memberships(self, user_id: uuid.UUID) -> list[tuple[Organization, MembershipRole]]:
        query = (
            select(Organization, Membership.role)
            .join(Membership, Membership.organization_id == Organization.id)
            .where(Membership.user_id == user_id)
            .order_by(Organization.id)
        )
        return [(org, role) for org, role in (await self._session.execute(query)).all()]

    async def add_refresh_token(
        self, user_id: uuid.UUID, family_id: uuid.UUID, token_hash: str, expires_at: datetime
    ) -> None:
        self._session.add(
            RefreshToken(user_id=user_id, family_id=family_id, token_hash=token_hash, expires_at=expires_at)
        )
        await self._session.flush()

    async def refresh_token_for_update(self, token_hash: str) -> RefreshToken | None:
        query = select(RefreshToken).where(RefreshToken.token_hash == token_hash).with_for_update()
        return await self._session.scalar(query)

    async def mark_used(self, token_id: uuid.UUID, now: datetime) -> None:
        await self._session.execute(
            update(RefreshToken).where(RefreshToken.id == token_id).values(used_at=now, last_seen_at=now)
        )

    async def revoke_family(self, family_id: uuid.UUID, now: datetime) -> None:
        await self._session.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )

    async def add_api_token(
        self,
        user_id: uuid.UUID,
        name: str,
        prefix: str,
        token_hash: str,
        expires_at: datetime | None,
        scope: TokenScope = TokenScope.WRITE,
    ) -> ApiToken:
        token = ApiToken(
            user_id=user_id, name=name, prefix=prefix, token_hash=token_hash, expires_at=expires_at, scope=scope
        )
        self._session.add(token)
        await self._session.flush()
        return token

    async def api_tokens(self, user_id: uuid.UUID) -> list[ApiToken]:
        query = select(ApiToken).where(ApiToken.user_id == user_id).order_by(ApiToken.id.desc())
        return list((await self._session.scalars(query)).all())

    async def active_api_token_count(self, user_id: uuid.UUID, now: datetime) -> int:
        query = select(func.count()).where(
            ApiToken.user_id == user_id,
            ApiToken.revoked_at.is_(None),
            or_(ApiToken.expires_at.is_(None), ApiToken.expires_at > now),
        )
        return int(await self._session.scalar(query) or 0)

    async def api_token(self, user_id: uuid.UUID, token_id: uuid.UUID) -> ApiToken | None:
        return await self._session.scalar(select(ApiToken).where(ApiToken.id == token_id, ApiToken.user_id == user_id))

    # --- organizations, members ------------------------------------------------------------------

    async def organization(self, organization_id: uuid.UUID) -> Organization | None:
        return await self._session.get(Organization, organization_id)

    async def role_in(self, user_id: uuid.UUID, organization_id: uuid.UUID) -> MembershipRole | None:
        query = select(Membership.role).where(
            Membership.user_id == user_id, Membership.organization_id == organization_id
        )
        return await self._session.scalar(query)

    async def members(self, organization_id: uuid.UUID) -> list[tuple[Membership, User]]:
        query = (
            select(Membership, User)
            .join(User, User.id == Membership.user_id)
            .where(Membership.organization_id == organization_id)
            .order_by(Membership.id)
        )
        return [(m, u) for m, u in (await self._session.execute(query)).all()]

    async def add_membership(self, organization_id: uuid.UUID, user_id: uuid.UUID, role: MembershipRole) -> None:
        self._session.add(Membership(organization_id=organization_id, user_id=user_id, role=role))
        await self._session.flush()

    async def set_role(self, organization_id: uuid.UUID, user_id: uuid.UUID, role: MembershipRole) -> None:
        await self._session.execute(
            update(Membership)
            .where(Membership.organization_id == organization_id, Membership.user_id == user_id)
            .values(role=role)
        )

    async def remove_membership(self, organization_id: uuid.UUID, user_id: uuid.UUID) -> None:
        await self._session.execute(
            delete(Membership).where(Membership.organization_id == organization_id, Membership.user_id == user_id)
        )

    async def owner_count(self, organization_id: uuid.UUID) -> int:
        query = select(func.count()).where(
            Membership.organization_id == organization_id, Membership.role == MembershipRole.OWNER
        )
        return int(await self._session.scalar(query) or 0)

    async def lock_organization(self, organization_id: uuid.UUID) -> None:
        """Serialize changes of one workspace's members, so two admins can't both remove the last owner."""
        await self._session.execute(select(Organization.id).where(Organization.id == organization_id).with_for_update())

    # --- invites ---------------------------------------------------------------------------------

    async def add_invite(self, invite: Invite) -> Invite:
        self._session.add(invite)
        await self._session.flush()
        return invite

    async def invites(self, organization_id: uuid.UUID) -> list[tuple[Invite, str | None]]:
        query = (
            select(Invite, User.name)
            .outerjoin(User, User.id == Invite.invited_by)
            .where(Invite.organization_id == organization_id)
            .order_by(Invite.id.desc())
            .limit(500)
        )
        return [(i, name) for i, name in (await self._session.execute(query)).all()]

    async def invite(self, organization_id: uuid.UUID, invite_id: uuid.UUID) -> Invite | None:
        return await self._session.scalar(
            select(Invite).where(Invite.id == invite_id, Invite.organization_id == organization_id).with_for_update()
        )

    async def invite_by_token(self, token_hash: str, for_update: bool = False) -> Invite | None:
        query = select(Invite).where(Invite.token_hash == token_hash)
        return await self._session.scalar(query.with_for_update() if for_update else query)

    async def open_invite_count(self, organization_id: uuid.UUID, now: datetime) -> int:
        query = select(func.count()).where(
            Invite.organization_id == organization_id,
            Invite.accepted_at.is_(None),
            Invite.revoked_at.is_(None),
            Invite.expires_at > now,
        )
        return int(await self._session.scalar(query) or 0)

    async def revoke_open_invites_for(self, organization_id: uuid.UUID, email: str, now: datetime) -> None:
        await self._session.execute(
            update(Invite)
            .where(
                Invite.organization_id == organization_id,
                Invite.email == email,
                Invite.accepted_at.is_(None),
                Invite.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )

    # --- email verification and external identities -----------------------------------------------

    async def add_verification(self, user_id: uuid.UUID, token_hash: str, expires_at: datetime) -> None:
        self._session.add(EmailVerification(user_id=user_id, token_hash=token_hash, expires_at=expires_at))
        await self._session.flush()

    async def verification_for_update(self, token_hash: str) -> EmailVerification | None:
        query = select(EmailVerification).where(EmailVerification.token_hash == token_hash).with_for_update()
        return await self._session.scalar(query)

    async def mark_verified(self, user_id: uuid.UUID, now: datetime) -> None:
        await self._session.execute(
            update(User).where(User.id == user_id, User.email_verified_at.is_(None)).values(email_verified_at=now)
        )
        await self._session.execute(
            update(EmailVerification)
            .where(EmailVerification.user_id == user_id, EmailVerification.used_at.is_(None))
            .values(used_at=now)
        )

    async def identity(self, provider: str, subject: str) -> ExternalIdentity | None:
        return await self._session.scalar(
            select(ExternalIdentity).where(ExternalIdentity.provider == provider, ExternalIdentity.subject == subject)
        )

    async def add_identity(self, user_id: uuid.UUID, provider: str, subject: str, email: str) -> None:
        self._session.add(ExternalIdentity(user_id=user_id, provider=provider, subject=subject, email=email))
        await self._session.flush()

    async def create_external_user(
        self, email: str, name: str, password_hash: str, org_name: str, now: datetime
    ) -> User:
        user = await self.create_user_with_personal_org(email, name, password_hash, org_name)
        user.email_verified_at = now
        return user
