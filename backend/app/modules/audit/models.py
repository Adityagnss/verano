"""
The audit_events table: one row per recorded change, written once and never changed.

The organization, project and actor are plain ids (no foreign keys), and the actor's name is copied into the row,
so an entry still reads correctly after a person leaves or a project is deleted. The migration adds a database
trigger that refuses UPDATE and DELETE, so append-only holds even for code that bypasses this module.
"""

import uuid
from typing import Any

from sqlalchemy import Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, CreatedAtMixin, IdMixin


class AuditEvent(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index(None, "organization_id", "id"),
        Index(None, "organization_id", "action", "id"),
        Index(None, "organization_id", "actor_id", "id"),
        Index(None, "organization_id", "created_at"),
    )

    organization_id: Mapped[uuid.UUID]
    project_id: Mapped[uuid.UUID | None]
    actor_id: Mapped[uuid.UUID | None]
    actor_name: Mapped[str | None] = mapped_column(String(320))
    action: Mapped[str] = mapped_column(String(64))
    target_type: Mapped[str | None] = mapped_column(String(32))
    target_id: Mapped[str | None] = mapped_column(String(64))
    summary: Mapped[str] = mapped_column(Text)
    details: Mapped[dict[str, Any]]
