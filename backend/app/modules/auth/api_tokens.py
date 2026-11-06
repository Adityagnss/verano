"""
Personal API token check, used by `get_principal` for bearer tokens that start with `vrn_`.

Looks the token's SHA-256 digest up and accepts it only if it is not revoked and not past
its expiry. Every failure gives the same message, so a caller can't tell an unknown token
from an expired or revoked one. `last_used_at` is refreshed at most every few minutes, so a
busy CI job does not write on every request. It opens its own short session, apart from the
request's.
"""

from datetime import timedelta

from sqlalchemy import or_, select, update

from app.core.database import Database
from app.core.errors import AuthenticationFailed
from app.core.security import Principal, digest_token, utcnow
from app.modules.auth.models import ApiToken

INVALID_TOKEN = "This API token is invalid, expired or revoked."
TOUCH_EVERY = timedelta(minutes=5)


class ApiTokenAuthenticator:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def verify(self, raw_token: str) -> Principal:
        now = utcnow()
        async with self._database.sessions() as session:
            token = await session.scalar(
                select(ApiToken).where(
                    ApiToken.token_hash == digest_token(raw_token),
                    ApiToken.revoked_at.is_(None),
                    or_(ApiToken.expires_at.is_(None), ApiToken.expires_at > now),
                )
            )
            if token is None:
                raise AuthenticationFailed(INVALID_TOKEN)
            await session.execute(
                update(ApiToken)
                .where(
                    ApiToken.id == token.id,
                    or_(ApiToken.last_used_at.is_(None), ApiToken.last_used_at < now - TOUCH_EVERY),
                )
                .values(last_used_at=now)
            )
            await session.commit()
            return Principal(
                user_id=token.user_id,
                via_api_token=True,
                read_only=token.scope == "read",
                project_id=token.project_id,
            )
