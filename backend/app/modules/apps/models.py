"""
Apps tables: app_targets and app_calls (ADR 0024).

An app target is the user's own application, reached over HTTP, that an experiment can test next to
models. It is stored as a credential of the provider `app` (its secret headers, encrypted like a
provider key) plus one model profile, so the planner, the executor and the results treat it as one more
model column; this table holds what is specific to an app: the address, the request template and where
to find the answer, retrieved chunks and tool calls in its reply. Every call to the app is recorded in
`app_calls` with the secret parts redacted.
"""

import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, CreatedAtMixin, IdMixin
from app.core.ids import uuid7


class AppTarget(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "app_targets"
    __table_args__ = (Index(None, "project_id", "id"), Index(None, "credential_id", unique=True))

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    credential_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("provider_credentials.id", ondelete="CASCADE"))
    model_profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("model_profiles.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    url: Mapped[str] = mapped_column(String(1000))
    method: Mapped[str] = mapped_column(String(8))
    mode: Mapped[str] = mapped_column(String(16))
    request_template: Mapped[str] = mapped_column(Text)
    answer_path: Mapped[str] = mapped_column(String(500))
    chunks_path: Mapped[str | None] = mapped_column(String(500))
    tool_calls_path: Mapped[str | None] = mapped_column(String(500))
    cost_path: Mapped[str | None] = mapped_column(String(500))
    auth_kind: Mapped[str] = mapped_column(String(16))
    header_names: Mapped[list[Any]]
    timeout_s: Mapped[float]
    concurrency: Mapped[int]
    retries: Mapped[int]


class AppCall(CreatedAtMixin, Base):
    __tablename__ = "app_calls"
    __table_args__ = (Index(None, "experiment_id", "test_case_run_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    experiment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("experiments.id", ondelete="CASCADE"))
    test_case_run_id: Mapped[uuid.UUID]
    app_target_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_targets.id", ondelete="CASCADE"))
    turn: Mapped[int] = mapped_column(default=0, server_default="0")
    request_body: Mapped[str | None] = mapped_column(Text)
    status_code: Mapped[int | None]
    response_body: Mapped[str | None] = mapped_column(Text)
    truncated: Mapped[bool] = mapped_column(default=False, server_default="false")
    latency_ms: Mapped[int | None]
    error: Mapped[str | None] = mapped_column(Text)
