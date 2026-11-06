"""
Organization tables: the shared key store and the workspace settings.

`organization_keys` holds a provider key once, encrypted like every key (Fernet, last four characters for display).
A project uses it through an ordinary `provider_credentials` row whose `organization_key_id` points here; rotation
rewrites the stored key of every such row in one transaction (ADR 0030). `organization_settings` holds the
workspace's monthly spending limit.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Index, LargeBinary, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, CreatedAtMixin, IdMixin


class OrganizationKey(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "organization_keys"
    __table_args__ = (Index(None, "organization_id", "id"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(64))
    label: Mapped[str | None] = mapped_column(String(120))
    encrypted_key: Mapped[bytes] = mapped_column(LargeBinary)
    key_last4: Mapped[str | None] = mapped_column(String(4))
    base_url: Mapped[str | None] = mapped_column(String(500))
    rpm_limit: Mapped[int | None]
    tpm_limit: Mapped[int | None]
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    rotated_at: Mapped[datetime | None]
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class OrganizationSettings(Base):
    __tablename__ = "organization_settings"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True
    )
    monthly_spend_limit: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
