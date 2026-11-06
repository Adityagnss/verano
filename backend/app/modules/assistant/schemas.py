"""
Assistant schemas: optimization session and candidate outcomes, the session's stage
(analyzing failures → testing candidates on the optimize split → confirming the best on
the holdout split → done), what the Improve screen shows, and the JSON the improvement
model must return for failure groups and candidate prompts.
"""

import uuid
from datetime import datetime
from decimal import Decimal
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
    QUICK = "quick"
    CONFIRMING = "confirming"
    DONE = "done"
    FAILED = "failed"
    STOPPED = "stopped"


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
    # how many rounds to run in one session (left out: the server's setting, 3 by default)
    rounds: int | None = Field(default=None, ge=1, le=6)
    # candidates written per round
    population: int | None = Field(default=None, ge=2, le=8)
    # try every candidate on a small sample first and run the full test only on the best ones
    quick_check: bool | None = None
    # stop starting new calls in any test of this session at this many dollars (resume from the Run screen)
    budget_cap: Decimal | None = Field(default=None, gt=0)
    # the quality gain worth detecting (0.1 = 10 points); sizes the quick check and the held-back test
    target_effect: float | None = Field(default=None, gt=0, le=1)


class ReadinessOut(BaseModel):
    """Whether Improve can change what this experiment tests, said in plain words."""

    ready: bool
    message: str
    apps: list[str] = []
    apps_not_taking_the_prompt: list[str] = []


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
    prompt_version_id: uuid.UUID | None
    strategy: str
    diff: str
    system_template: str | None = None
    user_template: str | None = None
    change_reasons: list[Any]
    target_cluster_ids: list[Any]
    outcome: CandidateOutcome
    optimize_experiment_id: uuid.UUID | None
    holdout_experiment_id: uuid.UUID | None
    optimize_quality: float | None
    holdout_quality: float | None
    verdict: VerdictOut | None = None
    round: int = 1
    parent_candidate_id: uuid.UUID | None = None
    quick_experiment_id: uuid.UUID | None = None
    quick_quality: float | None = None
    is_winner: bool = False
    metrics: dict[str, Any] | None = None
    rejection_reason: str | None = None
    # plain words for the tree: "Proven on held-back cases" or "Not proven ..."
    label: str | None = None


class RoundOut(BaseModel):
    round: int
    winner_candidate_id: uuid.UUID | None
    proven: bool
    label: str


class SizingOut(BaseModel):
    target_effect: float
    spread: float
    needed_cases: int
    holdout_cases: int
    enough: bool
    quick_sample: int | None
    message: str


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
    # set when a candidate was saved and tested in one go
    started_experiment_id: uuid.UUID | None = None
    # the prompt label Accept moved to the accepted version, when the prompt is set to move one
    moved_label: str | None = None
    focus: str = "quality"
    round_limit: int = 1
    current_round: int = 1
    quick_check: bool = False
    population: int = 3
    rounds: list[RoundOut] = []
    sizing: SizingOut | None = None
    final_candidate_id: uuid.UUID | None = None
    # the final winner against the very first prompt on the held-back cases (several rounds only)
    versus_first: VerdictOut | None = None
    paused_experiment_ids: list[uuid.UUID] = []


class ImprovementSummary(BaseModel):
    """One earlier improvement in the history list: how it ended and which candidate did best."""

    id: uuid.UUID
    stage: SessionStage
    message: str | None
    baseline_experiment_id: uuid.UUID | None
    created_at: datetime
    candidate_count: int
    best_strategy: str | None
    best_outcome: CandidateOutcome | None


class CandidateRef(BaseModel):
    """The improvement and candidate an experiment was made to test."""

    session_id: uuid.UUID
    candidate_id: uuid.UUID
    strategy: str
    outcome: CandidateOutcome


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


class ClusterName(BaseModel):
    cluster: int
    name: str = Field(min_length=1, max_length=200)
    hypothesis: str


class ClusterNames(BaseModel):
    groups: list[ClusterName] = Field(min_length=1)
