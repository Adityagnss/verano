"""
External results: a table for check results computed outside Verano (for example by `pytest` in a user's own
repository) and sent in through the API, so they can be seen next to the runs Verano did itself.
"""

import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, CreatedAtMixin, IdMixin


class ExternalRun(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "external_runs"
    __table_args__ = (Index(None, "project_id", "id"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    source: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(200))
    passed: Mapped[int]
    failed: Mapped[int]
    cases: Mapped[list[Any]]
    details: Mapped[dict[str, Any]]
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
