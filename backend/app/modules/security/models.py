"""
Security tables: security_packs and security_cases.

A pack is one generated set of attack cases for one prompt version. Its cases stay drafts (here, not in the project's
test cases) until a person approves them; approving the pack freezes the approved cases into a separate "security"
dataset version, so attacks never mix into the quality test cases (ADR 0035).
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, CreatedAtMixin, IdMixin


class SecurityPack(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "security_packs"
    __table_args__ = (Index(None, "project_id", "id"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    prompt_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("prompt_versions.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(16))  # generating, draft, approved, failed
    canary: Mapped[str] = mapped_column(String(64))
    categories: Mapped[list[Any]]
    per_category: Mapped[int]
    tool_app: Mapped[bool] = mapped_column(default=False, server_default="false")
    generator: Mapped[dict[str, Any] | None]
    message: Mapped[str | None] = mapped_column(Text)
    dataset_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("dataset_versions.id", ondelete="SET NULL"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    lease_expires_at: Mapped[datetime | None]


class SecurityCase(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "security_cases"
    __table_args__ = (Index(None, "pack_id", "id"),)

    pack_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("security_packs.id", ondelete="CASCADE"))
    category: Mapped[str] = mapped_column(String(64))
    attack: Mapped[str] = mapped_column(Text)
    inputs: Mapped[dict[str, Any]]
    safe_behaviour: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(16))  # built_in or model
    status: Mapped[str] = mapped_column(String(16))  # draft, approved, rejected
    position: Mapped[int]
