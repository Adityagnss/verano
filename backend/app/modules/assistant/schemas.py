"""
Assistant schemas: optimization session and candidate outcomes, the session's stage
(analyzing failures → testing candidates on the optimize split → confirming the best on
the holdout split → done), what the Improve screen shows, and the JSON the improvement
model must return for failure groups and candidate prompts.
"""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.modules.evaluation.schemas import ComparisonOut, JudgeChoice


class OptimizationStatus(StrEnum):
    ACTIVE = "active"
    CLOSED = "closed"


class CandidateOutcome(StrEnum):
    PENDING = "pending"
    BETTER = "better"
    NOT_BETTER = "not_better"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class SessionStage(StrEnum):
    ANALYZING = "analyzing"
    TESTING = "testing"
    CONFIRMING = "confirming"
    DONE = "done"
    FAILED = "failed"


class Reason(StrEnum):
    """Why a candidate is or is not proven better than the current prompt."""

    PROVEN = "proven"
    WORSE = "worse"
    NOT_PROVEN = "not_proven"
    TOO_FEW_CASES = "too_few_cases"
    DIFFERENT_JUDGE = "different_judge"
    UNJUDGED = "unjudged"


class VerdictOut(BaseModel):
    """The evidence behind a candidate's outcome: the holdout comparison and the plain-words conclusion."""

    reason: Reason
    message: str
    minimum_cases: int
    comparison: ComparisonOut | None


class ImproveRequest(BaseModel):
    experiment_id: uuid.UUID
    # The model that writes the improvements; left out, the experiment's judge does
    writer: JudgeChoice | None = None


class ClusterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    hypothesis: str
    rule_tag: str | None
    size: int
    affected_models: list[Any]
    categories: list[Any]
    example_case_ids: list[Any]


class CandidateOut(BaseModel):
    id: uuid.UUID
    prompt_version_id: uuid.UUID
    strategy: str
    diff: str
    change_reasons: list[Any]
    target_cluster_ids: list[Any]
    outcome: CandidateOutcome
    optimize_experiment_id: uuid.UUID | None
    holdout_experiment_id: uuid.UUID | None
    optimize_quality: float | None
    holdout_quality: float | None
    verdict: VerdictOut | None = None


class ImprovementOut(BaseModel):
    id: uuid.UUID
    status: OptimizationStatus
    stage: SessionStage
    message: str | None
    writer_model: str | None = None
    root_prompt_version_id: uuid.UUID
    baseline_experiment_id: uuid.UUID | None
    baseline_optimize_quality: float | None
    baseline_holdout_quality: float | None
    clusters: list[ClusterOut]
    candidates: list[CandidateOut]
    created_at: datetime


# What the improvement model must return (validated by the gateway's complete_json).
class FailureGroup(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    hypothesis: str
    cases: list[int]


class FailureGroups(BaseModel):
    groups: list[FailureGroup] = Field(min_length=1)


class CandidateDraft(BaseModel):
    strategy: str = Field(min_length=1, max_length=64)
    system_template: str | None = None
    user_template: str | None = None
    change_reasons: list[str] = []
    target_groups: list[str] = []


class CandidateDrafts(BaseModel):
    candidates: list[CandidateDraft] = Field(min_length=1)
