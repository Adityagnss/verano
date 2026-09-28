"""
Evaluation schemas: evaluation-run lifecycle and trigger, and the versioned evaluator set
(its evaluators, thresholds, weights and editable judge rubrics).
"""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EvaluationRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class EvaluationTrigger(StrEnum):
    INITIAL = "initial"
    RESCORE = "rescore"


class EvaluatorConfigIn(BaseModel):
    evaluator_name: str = Field(min_length=1, max_length=100)
    evaluator_version: str = Field(min_length=1, max_length=32)
    config: dict[str, Any] = {}
    threshold: float = Field(ge=0.0, le=1.0)
    weight: float = Field(gt=0.0)
    required: bool = False


class EvaluatorConfigOut(EvaluatorConfigIn):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    position: int


class EvaluatorSetUpdate(BaseModel):
    evaluators: list[EvaluatorConfigIn] = Field(min_length=1)
    change_reason: str | None = Field(default=None, max_length=2000)


class EvaluatorSetVersionOut(BaseModel):
    id: uuid.UUID
    evaluator_set_id: uuid.UUID
    version: int
    change_reason: str | None
    evaluators: list[EvaluatorConfigOut]
    created_at: datetime


class RescoreRequest(BaseModel):
    evaluator_set_version_id: uuid.UUID | None = None


class EvaluationRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    experiment_id: uuid.UUID
    evaluator_set_version_id: uuid.UUID
    status: EvaluationRunStatus
    trigger: EvaluationTrigger
    created_at: datetime
    completed_at: datetime | None


class ModelMetricsOut(BaseModel):
    model_profile_id: uuid.UUID
    model: str
    cases: int
    quality: float
    pass_rate: float
    consistency: float | None
    latency_ms: float | None
    cost: Decimal | None
    cost_per_call: Decimal | None
    failed_calls: int


class ResultsOut(BaseModel):
    experiment_id: uuid.UUID
    evaluation_run: EvaluationRunOut | None
    evaluation_runs: list[EvaluationRunOut]
    models: list[ModelMetricsOut]


class ScoreOut(BaseModel):
    evaluator_name: str
    value: float
    passed: bool
    reason: str


class CaseOutput(BaseModel):
    test_case_run_id: uuid.UUID
    model_profile_id: uuid.UUID
    model: str
    run_number: int
    output: str | None
    error: str | None
    passed: bool
    quality: float
    latency_ms: int | None
    cost: Decimal | None
    scores: list[ScoreOut]


class CaseResultOut(BaseModel):
    dataset_item_id: uuid.UUID
    inputs: dict[str, Any]
    expected_output: str | None
    rubric: list[Any] | None
    category: str
    source: str
    split: str | None
    outputs: list[CaseOutput]
