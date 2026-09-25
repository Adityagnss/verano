"""
The failure_clusters table.

One row per named cluster of failed cases from one evaluation run: a name and root-cause
hypothesis (from one LLM call per cluster), its size, the models and categories it
affects, example test-case-run ids, and the rule tag when the cluster came from a free
rule tagger rather than embedding clustering.
"""

import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, CreatedAtMixin, IdMixin


class FailureCluster(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "failure_clusters"
    __table_args__ = (Index(None, "evaluation_run_id", "id"),)

    experiment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("experiments.id", ondelete="CASCADE"))
    evaluation_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evaluation_runs.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    hypothesis: Mapped[str] = mapped_column(Text)
    rule_tag: Mapped[str | None] = mapped_column(String(64))
    size: Mapped[int]
    affected_models: Mapped[list[Any]]
    categories: Mapped[list[Any]]
    example_case_ids: Mapped[list[Any]]
    llm_call_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("llm_calls.id", ondelete="SET NULL"))
