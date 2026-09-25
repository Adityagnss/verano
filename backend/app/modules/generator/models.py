"""
The task_specs table.

Stores each Task Spec draft and its confirmed form as JSON validated by
`generator.schemas.TaskSpec`, with the schema version, the prompt version it describes,
and the model / LLM call that produced the draft.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, CreatedAtMixin, IdMixin, str_enum
from app.modules.generator.schemas import TaskSpecStatus


class TaskSpecRecord(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "task_specs"
    __table_args__ = (Index(None, "project_id", "id"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    prompt_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("prompt_versions.id", ondelete="CASCADE"))
    spec: Mapped[dict[str, Any]]
    schema_version: Mapped[int]
    status: Mapped[TaskSpecStatus] = mapped_column(str_enum(TaskSpecStatus, "task_spec_status"))
    generator_credential_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("provider_credentials.id", ondelete="SET NULL")
    )
    generator_model: Mapped[str | None] = mapped_column(String(300))
    llm_call_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("llm_calls.id", ondelete="SET NULL"))
    confirmed_at: Mapped[datetime | None]
