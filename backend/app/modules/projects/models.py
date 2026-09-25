"""
Projects table.

A project belongs to one organization. Every other project-scoped table references
`projects.id` with ON DELETE CASCADE, so deleting a project removes everything in it.
"""

import uuid

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, CreatedAtMixin, IdMixin


class Project(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (Index(None, "organization_id", "id"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
