"""
Engine tables: experiments, experiment_events and test_case_runs.

An experiment stores references to the exact prompt, dataset and evaluator set versions
plus a `snapshot` of model profiles and library versions, so it can be reproduced; it is
immutable once started (a config change creates a new experiment). `experiment_events` is
the audit trail of every status transition.
`test_case_runs` holds one row per matrix cell (item × model × param set × run) with a
deterministic id, keyed by (experiment_id, id): UUIDv7 experiment ids are time-ordered,
so this primary key is ready for range partitioning by experiment creation time
(ADR 0005) and every write can be an idempotent INSERT ... ON CONFLICT DO NOTHING.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, CreatedAtMixin, IdMixin, str_enum
from app.modules.engine.schemas import ExperimentOrigin, ExperimentStatus, RunStatus, SplitScope


class Experiment(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "experiments"
    __table_args__ = (Index(None, "project_id", "id"), Index(None, "status"))

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[ExperimentStatus] = mapped_column(str_enum(ExperimentStatus, "experiment_status"))
    origin: Mapped[ExperimentOrigin] = mapped_column(str_enum(ExperimentOrigin, "experiment_origin"))
    prompt_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("prompt_versions.id", ondelete="RESTRICT"))
    dataset_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("dataset_versions.id", ondelete="RESTRICT"))
    evaluator_set_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evaluator_set_versions.id", ondelete="RESTRICT")
    )
    split_scope: Mapped[SplitScope] = mapped_column(str_enum(SplitScope, "split_scope"))
    config: Mapped[dict[str, Any]]
    snapshot: Mapped[dict[str, Any]]
    estimate: Mapped[dict[str, Any] | None]
    budget_cap: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    total_calls: Mapped[int] = mapped_column(default=0, server_default="0")
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    started_at: Mapped[datetime | None]
    completed_at: Mapped[datetime | None]


class ExperimentEvent(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "experiment_events"
    __table_args__ = (Index(None, "experiment_id", "id"),)

    experiment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("experiments.id", ondelete="CASCADE"))
    from_status: Mapped[ExperimentStatus | None] = mapped_column(str_enum(ExperimentStatus, "experiment_event_from"))
    to_status: Mapped[ExperimentStatus] = mapped_column(str_enum(ExperimentStatus, "experiment_event_to"))
    reason: Mapped[str | None] = mapped_column(Text)


class TestCaseRun(CreatedAtMixin, Base):
    __test__ = False
    __tablename__ = "test_case_runs"
    __table_args__ = (
        Index(None, "experiment_id", "status"),
        Index(None, "experiment_id", "model_profile_id", "param_set_key"),
        Index(None, "experiment_id", "dataset_item_id"),
    )

    experiment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("experiments.id", ondelete="CASCADE"), primary_key=True)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    dataset_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("dataset_items.id", ondelete="RESTRICT"))
    prompt_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("prompt_versions.id", ondelete="RESTRICT"))
    model_profile_id: Mapped[uuid.UUID]
    credential_id: Mapped[uuid.UUID | None]
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(400))
    param_set_key: Mapped[str] = mapped_column(String(64))
    params: Mapped[dict[str, Any]]
    run_number: Mapped[int]
    status: Mapped[RunStatus] = mapped_column(str_enum(RunStatus, "run_status"))
    rendered_system_prompt: Mapped[str | None] = mapped_column(Text)
    rendered_user_prompt: Mapped[str | None] = mapped_column(Text)
    raw_output: Mapped[str | None] = mapped_column(Text)
    parsed_output: Mapped[dict[str, Any] | None]
    finish_reason: Mapped[str | None] = mapped_column(String(64))
    error_type: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(default=0, server_default="0")
    input_tokens: Mapped[int | None]
    output_tokens: Mapped[int | None]
    cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    latency_ms: Mapped[int | None]
    ttft_ms: Mapped[int | None]
    llm_call_id: Mapped[uuid.UUID | None]
    lease_expires_at: Mapped[datetime | None]
    started_at: Mapped[datetime | None]
    completed_at: Mapped[datetime | None]
    trace_id: Mapped[str | None] = mapped_column(String(32))
    span_id: Mapped[str | None] = mapped_column(String(16))
