"""
Evaluation tables: evaluator_sets, evaluator_set_versions, evaluator_configs,
evaluation_runs and scores.

Evaluator sets are versioned: editing a rubric or weight creates a new version, and every
EvaluationRun names the exact version it scored with. Generation outputs are never changed;
each scoring pass is its own EvaluationRun (`initial` or `rescore`) with its own Score rows,
so rescoring adds results instead of overwriting them (ADR 0004). Results may only be
compared across runs that used the same evaluator set version.
`human_labels` holds what people said about an answer (ADR 0017); a label sits beside the scores and never changes one.
`judge_cache` keeps a judge's result by the content it judged (ADR 0021).
`scores` is keyed by (experiment_id, id) like `test_case_runs`, ready for partitioning.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, ForeignKeyConstraint, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, CreatedAtMixin, IdMixin, str_enum
from app.core.ids import uuid7
from app.modules.evaluation.schemas import EvaluationRunStatus, EvaluationTrigger


class EvaluatorSet(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "evaluator_sets"
    __table_args__ = (Index(None, "project_id", "id"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))


class EvaluatorSetVersion(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "evaluator_set_versions"
    __table_args__ = (Index(None, "evaluator_set_id", "version", unique=True),)

    evaluator_set_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evaluator_sets.id", ondelete="CASCADE"))
    version: Mapped[int]
    change_reason: Mapped[str | None] = mapped_column(Text)
    judge: Mapped[dict[str, Any] | None]
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class EvaluatorConfig(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "evaluator_configs"
    __table_args__ = (Index(None, "evaluator_set_version_id", "position", unique=True),)

    evaluator_set_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evaluator_set_versions.id", ondelete="CASCADE")
    )
    position: Mapped[int]
    evaluator_name: Mapped[str] = mapped_column(String(100))
    evaluator_version: Mapped[str] = mapped_column(String(32))
    config: Mapped[dict[str, Any]]
    threshold: Mapped[float]
    weight: Mapped[float]
    required: Mapped[bool]


class EvaluationRun(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "evaluation_runs"
    __table_args__ = (Index(None, "experiment_id", "id"),)

    experiment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("experiments.id", ondelete="CASCADE"))
    evaluator_set_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evaluator_set_versions.id", ondelete="RESTRICT")
    )
    status: Mapped[EvaluationRunStatus] = mapped_column(str_enum(EvaluationRunStatus, "evaluation_run_status"))
    trigger: Mapped[EvaluationTrigger] = mapped_column(str_enum(EvaluationTrigger, "evaluation_trigger"))
    completed_at: Mapped[datetime | None]
    lease_expires_at: Mapped[datetime | None]  # a worker's claim on a running pass (ADR 0037)


class Score(CreatedAtMixin, Base):
    __tablename__ = "scores"
    __table_args__ = (
        ForeignKeyConstraint(
            ["experiment_id", "test_case_run_id"],
            ["test_case_runs.experiment_id", "test_case_runs.id"],
            ondelete="CASCADE",
        ),
        Index(None, "evaluation_run_id", "test_case_run_id", "evaluator_name", unique=True),
        Index(None, "experiment_id", "evaluation_run_id"),
    )

    experiment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("experiments.id", ondelete="CASCADE"), primary_key=True)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    evaluation_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evaluation_runs.id", ondelete="CASCADE"))
    test_case_run_id: Mapped[uuid.UUID]
    evaluator_name: Mapped[str] = mapped_column(String(100))
    evaluator_version: Mapped[str] = mapped_column(String(32))
    value: Mapped[float]
    passed: Mapped[bool]
    status: Mapped[str] = mapped_column(String(16), default="scored", server_default="scored")
    required: Mapped[bool]
    weight: Mapped[float]
    reason: Mapped[str] = mapped_column(Text)
    extra: Mapped[dict[str, Any]]
    llm_call_id: Mapped[uuid.UUID | None]


class HumanLabel(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "human_labels"
    __table_args__ = (
        ForeignKeyConstraint(
            ["experiment_id", "test_case_run_id"],
            ["test_case_runs.experiment_id", "test_case_runs.id"],
            ondelete="CASCADE",
        ),
        Index(None, "experiment_id", "test_case_run_id", "user_id", unique=True),
        Index(None, "experiment_id"),
    )

    experiment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("experiments.id", ondelete="CASCADE"))
    test_case_run_id: Mapped[uuid.UUID]
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    verdict: Mapped[str] = mapped_column(String(16))
    note: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class JudgeCacheEntry(CreatedAtMixin, Base):
    __tablename__ = "judge_cache"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    evaluator_name: Mapped[str] = mapped_column(String(100))
    value: Mapped[float]
    passed: Mapped[bool]
    reason: Mapped[str] = mapped_column(Text)
    hits: Mapped[int] = mapped_column(default=0, server_default="0")
