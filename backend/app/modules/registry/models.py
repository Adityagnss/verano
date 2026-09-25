"""
Registry tables: provider_credentials and model_profiles.

A credential stores its API key only as Fernet ciphertext plus the last four characters
for display. Model profiles are upserted on every discovery keyed by (credential,
model_name), so re-discovery refreshes metadata without losing the user's selection.
Unknown prices are NULL, never 0; `price_source` records where a known price came from.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import ForeignKey, Index, LargeBinary, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, CreatedAtMixin, IdMixin, str_enum
from app.modules.registry.schemas import CredentialStatus, PriceSource

PRICE = Numeric(18, 8)


class ProviderCredential(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "provider_credentials"
    __table_args__ = (Index(None, "project_id", "id"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(64))
    label: Mapped[str | None] = mapped_column(String(120))
    encrypted_key: Mapped[bytes | None] = mapped_column(LargeBinary)
    key_last4: Mapped[str | None] = mapped_column(String(4))
    base_url: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[CredentialStatus] = mapped_column(str_enum(CredentialStatus, "credential_status"))
    status_message: Mapped[str | None] = mapped_column(Text)
    rpm_limit: Mapped[int | None]
    tpm_limit: Mapped[int | None]
    last_validated_at: Mapped[datetime | None]
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class ModelProfile(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "model_profiles"
    __table_args__ = (
        Index(None, "credential_id", "model_name", unique=True),
        Index(None, "project_id", "is_selected"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    credential_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("provider_credentials.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(64))
    model_name: Mapped[str] = mapped_column(String(300))
    display_name: Mapped[str] = mapped_column(String(300))
    litellm_model: Mapped[str] = mapped_column(String(400))
    context_window: Mapped[int | None]
    max_output_tokens: Mapped[int | None]
    parameters: Mapped[dict[str, Any]]
    supports_json_mode: Mapped[bool]
    supports_system_prompt: Mapped[bool]
    input_price_per_mtok: Mapped[Decimal | None] = mapped_column(PRICE)
    output_price_per_mtok: Mapped[Decimal | None] = mapped_column(PRICE)
    price_source: Mapped[PriceSource] = mapped_column(str_enum(PriceSource, "price_source"))
    is_selected: Mapped[bool] = mapped_column(default=False, server_default="false")
    discovered_at: Mapped[datetime] = mapped_column(server_default=func.now())
