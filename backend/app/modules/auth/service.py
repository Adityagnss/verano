"""
Auth use cases: sign-up, sign-in, refresh rotation, logout and membership lookups.

Sign-up creates the user together with a personal organization owned by them (no invites
in V1). When `VERANO_ALLOW_SIGNUP` is off, only the very first account can be created, so a
fresh self-hosted install can always be set up; an advisory lock makes that check race-free.
Sign-up, sign-in and refresh are throttled per client IP and (where an email is given) per
email, so bulk email probing and password guessing hit a 429 with Retry-After.
Every successful sign-in or refresh returns an `IssuedSession`: an access token for the
response body plus a new raw refresh token for the router to put in the cookie.
Refresh follows `domain.judge_refresh`; a reused token revokes its whole family and the
revocation is committed even though the request itself fails.
Other modules call `organization_ids` to authorize access to their resources.
"""

import hashlib
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import (
    AuthenticationFailed,
    Conflict,
    NotFound,
    PermissionDenied,
    TooManyRequests,
    ValidationFailed,
)
from app.core.ids import uuid7
from app.core.security import (
    API_TOKEN_PREFIX,
    AccessTokens,
    Passwords,
    Principal,
    digest_token,
    new_refresh_token,
    utcnow,
)
from app.core.throttle import FixedWindowLimiter
from app.modules.auth.domain import RefreshOutcome, RefreshTokenState, judge_refresh, normalize_email, password_problem
from app.modules.auth.models import User
from app.modules.auth.repository import AuthRepository
from app.modules.auth.schemas import (
    ApiTokenCreate,
    ApiTokenCreated,
    ApiTokenOut,
    AuthConfigOut,
    LoginRequest,
    MembershipRole,
    MeOut,
    OrganizationOut,
    SessionOut,
    SignupRequest,
    UserOut,
)

INVALID_LOGIN = "That email and password don't match an account. Check them and try again."
INVALID_REFRESH = "Your session has ended. Please sign in again."
SIGNUP_CLOSED = "Sign-up is turned off on this server. Ask its administrator for an account."
THROTTLED = "Too many attempts. Wait {seconds} seconds and try again."
TOKEN_FROM_SESSION = "Create API tokens while signed in, not with another API token."
TOKEN_LIMIT = "You already have {limit} active API tokens. Revoke one you no longer use first."
TOKEN_NOT_FOUND = "This API token doesn't exist."
MAX_ACTIVE_API_TOKENS = 20
TOKEN_PREFIX_CHARS = 8


@dataclass(frozen=True)
class IssuedSession:
    body: SessionOut
    refresh_token: str
    refresh_expires_at: datetime


class AuthService:
    def __init__(
        self,
        session: AsyncSession,
        passwords: Passwords,
        tokens: AccessTokens,
        settings: Settings,
        throttle: FixedWindowLimiter,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._session = session
        self._repo = AuthRepository(session)
        self._passwords = passwords
        self._tokens = tokens
        self._settings = settings
        self._throttle = throttle
        self._clock = clock

    async def config(self) -> AuthConfigOut:
        return AuthConfigOut(
            signup_open=self._settings.allow_signup or not await self._repo.has_users(),
            password_min_length=self._settings.password_min_length,
        )

    async def signup(self, request: SignupRequest, client_ip: str) -> IssuedSession:
        await self._check_throttle("signup", client_ip, request.email)
        if not self._settings.allow_signup:
            await self._repo.lock_signups()
            if await self._repo.has_users():
                raise PermissionDenied(SIGNUP_CLOSED)
        problem = password_problem(request.password, self._settings.password_min_length)
        if problem:
            raise ValidationFailed(problem, {"fields": [{"field": "password", "message": problem}]})
        email = normalize_email(request.email)
        if await self._repo.user_by_email(email):
            raise Conflict("An account with this email already exists. Sign in instead.")
        org_name = self._settings.personal_org_name_template.format(name=request.name)
        try:
            user = await self._repo.create_user_with_personal_org(
                email, request.name, self._passwords.hash(request.password), org_name
            )
        except IntegrityError as exc:
            raise Conflict("An account with this email already exists. Sign in instead.") from exc
        return await self._issue(user, family_id=uuid7())

    async def login(self, request: LoginRequest, client_ip: str) -> IssuedSession:
        await self._check_throttle("login", client_ip, request.email)
        user = await self._repo.user_by_email(normalize_email(request.email))
        if not self._passwords.verify(user.password_hash if user else None, request.password) or user is None:
            raise AuthenticationFailed(INVALID_LOGIN)
        return await self._issue(user, family_id=uuid7())

    async def refresh(self, raw_token: str | None, client_ip: str) -> IssuedSession:
        await self._check_throttle("refresh", client_ip, None)
        record = await self._repo.refresh_token_for_update(digest_token(raw_token)) if raw_token else None
        if record is None:
            raise AuthenticationFailed(INVALID_REFRESH)
        now = self._clock()
        state = RefreshTokenState(record.expires_at, record.used_at, record.revoked_at)
        outcome = judge_refresh(state, now)
        if outcome is RefreshOutcome.REUSED:
            await self._repo.revoke_family(record.family_id, now)
            await self._session.commit()
        if outcome is not RefreshOutcome.ROTATE:
            raise AuthenticationFailed(INVALID_REFRESH, {"reason": outcome.value})
        await self._repo.mark_used(record.id, now)
        user = await self._repo.user(record.user_id)
        if user is None:
            raise AuthenticationFailed(INVALID_REFRESH)
        return await self._issue(user, family_id=record.family_id)

    async def logout(self, raw_token: str | None) -> None:
        record = await self._repo.refresh_token_for_update(digest_token(raw_token)) if raw_token else None
        if record is not None:
            await self._repo.revoke_family(record.family_id, self._clock())

    async def me(self, principal: Principal) -> MeOut:
        user = await self._repo.user(principal.user_id)
        if user is None:
            raise NotFound("This account no longer exists.")
        return MeOut(user=UserOut.model_validate(user), organizations=await self.organizations(principal.user_id))

    async def organizations(self, user_id: uuid.UUID) -> list[OrganizationOut]:
        return [
            OrganizationOut(id=org.id, name=org.name, is_personal=org.is_personal, role=role)
            for org, role in await self._repo.memberships(user_id)
        ]

    async def organization_ids(self, user_id: uuid.UUID) -> list[uuid.UUID]:
        return [org.id for org in await self.organizations(user_id)]

    async def organization_members(self, organization_id: uuid.UUID) -> list[tuple[UserOut, MembershipRole]]:
        """The people in one organization and their roles. The caller has already been checked to belong to it."""
        return [(UserOut.model_validate(user), role) for user, role in await self._repo.members(organization_id)]

    async def personal_organization_id(self, user_id: uuid.UUID) -> uuid.UUID:
        personal = [org.id for org in await self.organizations(user_id) if org.is_personal]
        if not personal:
            raise NotFound("No personal workspace was found for this account.")
        return personal[0]

    async def create_api_token(self, principal: Principal, body: ApiTokenCreate) -> ApiTokenCreated:
        """A personal token for the CLI or CI. Only a signed-in session can make one, so a leaked
        token can't be used to mint more."""
        if principal.via_api_token:
            raise PermissionDenied(TOKEN_FROM_SESSION)
        now = self._clock()
        if await self._repo.active_api_token_count(principal.user_id, now) >= MAX_ACTIVE_API_TOKENS:
            raise Conflict(TOKEN_LIMIT.format(limit=MAX_ACTIVE_API_TOKENS))
        raw = API_TOKEN_PREFIX + new_refresh_token()
        expires_at = now + timedelta(days=body.expires_in_days) if body.expires_in_days else None
        token = await self._repo.add_api_token(
            principal.user_id, body.name, raw[:TOKEN_PREFIX_CHARS], digest_token(raw), expires_at
        )
        return ApiTokenCreated(**ApiTokenOut.model_validate(token).model_dump(), token=raw)

    async def list_api_tokens(self, principal: Principal) -> list[ApiTokenOut]:
        return [ApiTokenOut.model_validate(t) for t in await self._repo.api_tokens(principal.user_id)]

    async def revoke_api_token(self, principal: Principal, token_id: uuid.UUID) -> None:
        token = await self._repo.api_token(principal.user_id, token_id)
        if token is None:
            raise NotFound(TOKEN_NOT_FOUND)
        if token.revoked_at is None:
            token.revoked_at = self._clock()

    async def _check_throttle(self, action: str, client_ip: str, email: str | None) -> None:
        settings = self._settings
        checks = [(f"{action}:ip:{client_ip}", settings.auth_rate_limit_per_ip)]
        if email:
            email_key = hashlib.sha256(normalize_email(email).encode()).hexdigest()
            checks.append((f"{action}:email:{email_key}", settings.auth_rate_limit_per_email))
        for key, limit in checks:
            retry_after = await self._throttle.hit(f"auth:{key}", limit, settings.auth_rate_window_s)
            if retry_after is not None:
                raise TooManyRequests(THROTTLED.format(seconds=int(retry_after)), retry_after_s=retry_after)

    async def _issue(self, user: User, family_id: uuid.UUID) -> IssuedSession:
        now = self._clock()
        raw = new_refresh_token()
        expires_at = now + timedelta(seconds=self._settings.refresh_token_ttl_s)
        await self._repo.add_refresh_token(user.id, family_id, digest_token(raw), expires_at)
        body = SessionOut(
            access_token=self._tokens.issue(user.id, now),
            expires_in=self._tokens.ttl_s,
            user=UserOut.model_validate(user),
        )
        return IssuedSession(body=body, refresh_token=raw, refresh_expires_at=expires_at)
