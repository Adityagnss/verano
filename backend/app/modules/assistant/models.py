"""
Assistant tables: prompt_reviews, optimization_sessions and prompt_candidates.

A prompt review is the checklist result for one prompt version, optionally linked to the
evaluation run whose failures supply its evidence. An optimization session keeps the tree
V1 → candidates → V2 → ...: each candidate is itself a prompt version (source=assistant)
with its diff, per-change reasons, the clusters it targets, and the optimize-split and
holdout-split experiments that judged it.
"""

import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, CreatedAtMixin, IdMixin, str_enum
from app.modules.assistant.schemas import CandidateOutcome, OptimizationStatus


class PromptReview(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "prompt_reviews"
    __table_args__ = (Index(None, "prompt_version_id", "id"),)

    prompt_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("prompt_versions.id", ondelete="CASCADE"))
    evaluation_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("evaluation_runs.id", ondelete="SET NULL"))
    checks: Mapped[list[Any]]


class OptimizationSession(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "optimization_sessions"
    __table_args__ = (Index(None, "project_id", "id"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    root_prompt_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("prompt_versions.id", ondelete="CASCADE"))
    status: Mapped[OptimizationStatus] = mapped_column(str_enum(OptimizationStatus, "optimization_status"))
    baseline_experiment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("experiments.id", ondelete="SET NULL"))
    stage: Mapped[str] = mapped_column(String(32), default="analyzing", server_default="analyzing")
    message: Mapped[str | None] = mapped_column(Text)


class PromptCandidate(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "prompt_candidates"
    __table_args__ = (Index(None, "session_id", "id"),)

    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("optimization_sessions.id", ondelete="CASCADE"))
    base_prompt_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("prompt_versions.id", ondelete="CASCADE"))
    prompt_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("prompt_versions.id", ondelete="CASCADE"))
    strategy: Mapped[str] = mapped_column(String(64))
    target_cluster_ids: Mapped[list[Any]]
    diff: Mapped[str] = mapped_column(Text)
    change_reasons: Mapped[list[Any]]
    optimize_experiment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("experiments.id", ondelete="SET NULL"))
    holdout_experiment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("experiments.id", ondelete="SET NULL"))
    outcome: Mapped[CandidateOutcome] = mapped_column(str_enum(CandidateOutcome, "candidate_outcome"))
