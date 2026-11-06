"""
Prompt tables: prompts and prompt_versions.

Versions are immutable: every save inserts a new row with `parent_version_id`, a `source`
(manual or assistant) and a `change_reason`. A version holds a system template, a user
template, or both (a check constraint enforces at least one), plus the detected
`{{variables}}` and default parameters. A version with `is_candidate` is an improvement the
assistant is testing; it never becomes the prompt's latest version unless the user accepts
it, which saves a new, normal version. Candidates are numbered -1, -2, ... so they never use
up the version numbers people see.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, CreatedAtMixin, IdMixin, str_enum
from app.modules.prompts.schemas import PromptSource


class Prompt(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "prompts"
    __table_args__ = (Index(None, "project_id", "id"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    accept_moves_label: Mapped[str | None] = mapped_column(String(48))


class PromptVersion(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "prompt_versions"
    __table_args__ = (
        Index(None, "prompt_id", "version", unique=True),
        CheckConstraint("system_template IS NOT NULL OR user_template IS NOT NULL", name="has_template"),
    )

    prompt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("prompts.id", ondelete="CASCADE"))
    version: Mapped[int]
    parent_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("prompt_versions.id", ondelete="SET NULL"))
    system_template: Mapped[str | None] = mapped_column(Text)
    user_template: Mapped[str | None] = mapped_column(Text)
    variables: Mapped[list[Any]]
    default_params: Mapped[dict[str, Any]]
    source: Mapped[PromptSource] = mapped_column(str_enum(PromptSource, "prompt_source"))
    change_reason: Mapped[str | None] = mapped_column(Text)
    is_candidate: Mapped[bool] = mapped_column(default=False, server_default="false")
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class PromptLabel(IdMixin, CreatedAtMixin, Base):
    """A movable name (`production`, `staging`, ...) pointing at one saved version of a prompt."""

    __tablename__ = "prompt_labels"
    __table_args__ = (Index(None, "prompt_id", "name", unique=True), Index(None, "prompt_version_id"))

    prompt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("prompts.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(48))
    prompt_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("prompt_versions.id", ondelete="CASCADE"))
    moved_at: Mapped[datetime]


class PromptLabelMove(IdMixin, CreatedAtMixin, Base):
    """One entry of a label's history: where it pointed before, where it points now, who moved it and why."""

    __tablename__ = "prompt_label_moves"
    __table_args__ = (Index(None, "prompt_id", "id"),)

    prompt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("prompts.id", ondelete="CASCADE"))
    label: Mapped[str] = mapped_column(String(48))
    from_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("prompt_versions.id", ondelete="SET NULL"))
    to_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("prompt_versions.id", ondelete="SET NULL"))
    reason: Mapped[str] = mapped_column(String(16))
    moved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
