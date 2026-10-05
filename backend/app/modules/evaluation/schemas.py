"""
Evaluation schemas: evaluation-run lifecycle and trigger, and the versioned evaluator set
(its evaluators, thresholds, weights and editable judge rubrics).
"""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.evaluation.significance import Label


class EvaluationRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class EvaluationTrigger(StrEnum):
    INITIAL = "initial"
    RESCORE = "rescore"


MAX_CRITERIA_CHARS = 4000
MAX_STEPS = 10
MAX_STEP_CHARS = 1000
NEEDS_CRITERIA = "A judged check needs criteria or evaluation steps: say in words what a good answer is."
TOO_LONG = "Criteria can be at most {n} characters."
TOO_MANY_STEPS = f"Use at most {MAX_STEPS} evaluation steps, each at most {MAX_STEP_CHARS} characters."


class EvaluatorConfigIn(BaseModel):
    evaluator_name: str = Field(min_length=1, max_length=100)
    evaluator_version: str = Field(min_length=1, max_length=32)
    config: dict[str, Any] = {}
    threshold: float = Field(ge=0.0, le=1.0)
    weight: float = Field(gt=0.0)
    required: bool = False

    @model_validator(mode="after")
    def _judged_checks_say_what_to_judge(self) -> "EvaluatorConfigIn":
        if self.config.get("kind") != "deepeval":
            return self
        criteria = str(self.config.get("criteria") or "").strip()
        raw_steps = self.config.get("evaluation_steps") or []
        if not isinstance(raw_steps, list):
            raise ValueError(TOO_MANY_STEPS)
        steps = [str(step).strip() for step in raw_steps if str(step).strip()]
        if len(steps) > MAX_STEPS or any(len(step) > MAX_STEP_CHARS for step in steps):
            raise ValueError(TOO_MANY_STEPS)
        if len(criteria) > MAX_CRITERIA_CHARS:
            raise ValueError(TOO_LONG.format(n=MAX_CRITERIA_CHARS))
        if not criteria and not steps:
            raise ValueError(NEEDS_CRITERIA)
        cleaned = {k: v for k, v in self.config.items() if k not in ("criteria", "evaluation_steps")}
        if criteria:
            cleaned["criteria"] = criteria
        if steps:
            cleaned["evaluation_steps"] = steps
        self.config = cleaned
        return self


class EvaluatorConfigOut(EvaluatorConfigIn):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    position: int


class JudgeChoice(BaseModel):
    """The model that scores the judged checks, chosen on purpose and kept on the evaluator-set version."""

    credential_id: uuid.UUID
    model: str = Field(min_length=1, max_length=300)


class EvaluatorSetUpdate(BaseModel):
    evaluators: list[EvaluatorConfigIn] = Field(min_length=1)
    change_reason: str | None = Field(default=None, max_length=2000)
    judge: JudgeChoice | None = None


class EvaluatorSetVersionOut(BaseModel):
    id: uuid.UUID
    evaluator_set_id: uuid.UUID
    version: int
    change_reason: str | None
    judge: JudgeChoice | None
    evaluators: list[EvaluatorConfigOut]
    created_at: datetime


class RescoreRequest(BaseModel):
    """Score again with the same checks, a given version of them, or the same checks judged by another model."""

    evaluator_set_version_id: uuid.UUID | None = None
    judge: JudgeChoice | None = None
    evaluators: list[EvaluatorConfigIn] | None = Field(default=None, min_length=1)
    change_reason: str | None = Field(default=None, max_length=2000)


class JudgeCallOut(BaseModel):
    """One call the judge was asked to make about an answer, exactly as it was sent."""

    id: uuid.UUID
    evaluator: str | None
    evaluation_run_id: uuid.UUID | None
    preview: bool
    model: str
    status: str
    request_messages: list[Any]
    output_text: str | None
    error_message: str | None
    cost: Decimal | None
    created_at: datetime


class TryJudgeRequest(BaseModel):
    """Run one judged check on one stored answer, to see what the judge says before scoring everything again."""

    test_case_run_id: uuid.UUID
    evaluator: EvaluatorConfigIn
    judge: JudgeChoice | None = None


class TryJudgeEstimate(BaseModel):
    judge_calls: int
    judge_cost: Decimal | None
    price_known: bool
    judge_model: str | None


class EvaluationRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    experiment_id: uuid.UUID
    evaluator_set_version_id: uuid.UUID
    status: EvaluationRunStatus
    trigger: EvaluationTrigger
    created_at: datetime
    completed_at: datetime | None


class ComparisonOut(BaseModel):
    """How one set of results compares with another, case by case. `first` is the model (or the new version)
    being asked about, `second` what it is compared with; `difference` is first minus second."""

    label: Label
    cases: int
    only_first: int
    only_second: int
    difference: float | None
    low: float | None
    high: float | None
    level: float
    comparisons: int
    first_better: bool | None
    pass_rate_difference: float | None
    first_only_passed: int
    second_only_passed: int
    mcnemar_p: float | None
    method: str


class ModelMetricsOut(BaseModel):
    model_profile_id: uuid.UUID
    model: str
    cases: int
    judged_cases: int
    unscored_cases: int
    quality: float | None
    pass_rate: float | None
    consistency: float | None
    latency_ms: float | None
    cost: Decimal | None
    cost_per_call: Decimal | None
    failed_calls: int
    stability: float | None
    stable_cases: int
    compared_cases: int
    vs_best: ComparisonOut | None = None


class RescoreEstimate(BaseModel):
    judge_calls: int
    judge_cost: Decimal | None
    price_known: bool
    judge_model: str | None


class JudgeSuggestion(BaseModel):
    suggested: JudgeChoice | None
    reason: str
    candidates: list[JudgeChoice]


class ReplicationModel(BaseModel):
    model_profile_id: uuid.UUID
    model: str
    same: int
    compared: int
    skipped: int
    earlier_versions: list[str]
    versions: list[str]
    model_changed: bool
    quality: ComparisonOut | None = None


class ReplicationOut(BaseModel):
    """Did this experiment give the same answers as an earlier one with the same configuration?"""

    experiment_id: uuid.UUID
    against_id: uuid.UUID
    against_name: str
    same: int
    compared: int
    skipped: int
    model_changed: bool
    models: list[ReplicationModel]


class ResultsOut(BaseModel):
    experiment_id: uuid.UUID
    evaluation_run: EvaluationRunOut | None
    evaluation_runs: list[EvaluationRunOut]
    models: list[ModelMetricsOut]


class ScoreStatus(StrEnum):
    SCORED = "scored"
    UNSCORED = "unscored"


class ScoreOut(BaseModel):
    evaluator_name: str
    value: float
    passed: bool
    reason: str
    status: ScoreStatus = ScoreStatus.SCORED


class CaseOutput(BaseModel):
    test_case_run_id: uuid.UUID
    model_profile_id: uuid.UUID
    model: str
    run_number: int
    output: str | None
    error: str | None
    passed: bool
    quality: float
    judged: bool
    latency_ms: int | None
    cost: Decimal | None
    scores: list[ScoreOut]


class CaseAgreement(BaseModel):
    """One model's repeated answers to one test case: `same` of `runs` match."""

    model_profile_id: uuid.UUID
    same: int
    runs: int


class CaseResultOut(BaseModel):
    dataset_item_id: uuid.UUID
    inputs: dict[str, Any]
    expected_output: str | None
    rubric: list[Any] | None
    category: str
    source: str
    split: str | None
    outputs: list[CaseOutput]
    agreement: list[CaseAgreement]


class TryJudgeOut(BaseModel):
    score: ScoreOut
    calls: list[JudgeCallOut]
