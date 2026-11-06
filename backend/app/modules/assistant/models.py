"""
Assistant tables: prompt_reviews, optimization_sessions and prompt_candidates.

A prompt review is the checklist result for one prompt version, optionally linked to the
evaluation run whose failures supply its evidence. An optimization session keeps the tree
V1 → candidates → V2 → ...: each candidate is itself a prompt version (source=assistant)
with its diff, per-change reasons, the clusters it targets, and the optimize-split and
holdout-split experiments that judged it.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import ForeignKey, Index, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
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
    # The model that writes the failure groups and candidates; null means the baseline's judge
    writer: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # Phase 9 (ADR 0036): several rounds, a population per round, a quick check, a focus, a spend cap
    focus: Mapped[str] = mapped_column(String(16), default="quality", server_default="quality")
    focus_ref: Mapped[uuid.UUID | None]
    round_limit: Mapped[int] = mapped_column(default=1, server_default="1")
    current_round: Mapped[int] = mapped_column(default=1, server_default="1")
    population: Mapped[int] = mapped_column(default=3, server_default="3")
    quick_check: Mapped[bool] = mapped_column(default=False, server_default="false")
    target_effect: Mapped[float | None]
    budget_cap: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    # what the current round improves on: its prompt and the two scored experiments it is compared with
    round_prompt_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("prompt_versions.id", ondelete="SET NULL"))
    round_opt_exp_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("experiments.id", ondelete="SET NULL"))
    round_hold_exp_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("experiments.id", ondelete="SET NULL"))
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    lease_expires_at: Mapped[datetime | None]


class PromptCandidate(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "prompt_candidates"
    __table_args__ = (Index(None, "session_id", "id"),)

    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("optimization_sessions.id", ondelete="CASCADE"))
    base_prompt_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("prompt_versions.id", ondelete="CASCADE"))
    # null for a draft that was rejected before it became a version (its text is kept in `rejected_draft`)
    prompt_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("prompt_versions.id", ondelete="CASCADE"))
    strategy: Mapped[str] = mapped_column(String(64))
    target_cluster_ids: Mapped[list[Any]]
    diff: Mapped[str] = mapped_column(Text)
    change_reasons: Mapped[list[Any]]
    optimize_experiment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("experiments.id", ondelete="SET NULL"))
    holdout_experiment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("experiments.id", ondelete="SET NULL"))
    outcome: Mapped[CandidateOutcome] = mapped_column(str_enum(CandidateOutcome, "candidate_outcome"))
    verdict: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    round: Mapped[int] = mapped_column(default=1, server_default="1")
    # the earlier round's winner this candidate was written from (null in round 1: it grows from the first prompt)
    parent_candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("prompt_candidates.id", ondelete="SET NULL")
    )
    quick_experiment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("experiments.id", ondelete="SET NULL"))
    is_winner: Mapped[bool] = mapped_column(default=False, server_default="false")
    # quality, cost and length used for the Pareto sort, and the front the candidate landed on
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    rejected_draft: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
