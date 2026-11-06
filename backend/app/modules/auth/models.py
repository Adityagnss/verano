"""
Auth tables: users, organizations, memberships, refresh_tokens.

Refresh tokens are stored only as SHA-256 digests. Tokens issued by rotation share a
`family_id` with the token they replaced, so detecting the reuse of any old token can
revoke the whole chain in one UPDATE. Other modules reference users and organizations by
id only; they never import these classes.
"""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, CreatedAtMixin, IdMixin, str_enum
from app.modules.auth.schemas import MembershipRole


class User(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))


class Organization(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(200))
    is_personal: Mapped[bool]


class Membership(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "memberships"
    __table_args__ = (Index(None, "organization_id", "user_id", unique=True), Index(None, "user_id"))

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    role: Mapped[MembershipRole] = mapped_column(str_enum(MembershipRole, "membership_role"))


class RefreshToken(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = (Index(None, "family_id"), Index(None, "user_id"))

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    family_id: Mapped[uuid.UUID]
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime]
    used_at: Mapped[datetime | None]
    revoked_at: Mapped[datetime | None]
    last_seen_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ApiToken(IdMixin, CreatedAtMixin, Base):
    """A personal API token for the CLI and CI. Only the SHA-256 digest is stored; the token
    itself is shown once, when it is created. `prefix` is the first characters, to tell tokens apart."""

    __tablename__ = "api_tokens"
    __table_args__ = (Index(None, "user_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100))
    prefix: Mapped[str] = mapped_column(String(16))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    scope: Mapped[str] = mapped_column(String(16), server_default="full")
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    expires_at: Mapped[datetime | None]
    last_used_at: Mapped[datetime | None]
    revoked_at: Mapped[datetime | None]
