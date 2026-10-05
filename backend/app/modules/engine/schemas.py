"""
Engine schemas: experiment lifecycle states, per-call run states and split scope, and the
run configuration (models, runs per model, one parameter set per model, budget cap), the
cost preview, live progress per model, and the full record of each call.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.engine.sampling import MAX_RUNS, normalize_params


class ExperimentStatus(StrEnum):
    DRAFT = "draft"
    PLANNED = "planned"
    RUNNING = "running"
    PAUSED = "paused"
    EVALUATING = "evaluating"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class SplitScope(StrEnum):
    ALL = "all"
    OPTIMIZE = "optimize"
    HOLDOUT = "holdout"


class ExperimentOrigin(StrEnum):
    MANUAL = "manual"
    OPTIMIZATION = "optimization"


class ModelRun(BaseModel):
    model_profile_id: uuid.UUID
    runs: int = Field(default=1, ge=1, le=MAX_RUNS)
    params: dict[str, Any] = {}

    @field_validator("params")
    @classmethod
    def _sampling(cls, params: dict[str, Any]) -> dict[str, Any]:
        return normalize_params(params)


class ExperimentCreate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    dataset_version_id: uuid.UUID | None = None
    split_scope: SplitScope = SplitScope.ALL
    models: list[ModelRun] = Field(min_length=1)
    budget_cap: Decimal | None = Field(default=None, gt=0)


class ModelEstimate(BaseModel):
    model_profile_id: uuid.UUID
    display_name: str
    calls: int
    input_tokens: int
    output_tokens: int
    cost: Decimal | None


class ExperimentEstimate(BaseModel):
    cases: int
    calls: int
    input_tokens: int
    output_tokens: int
    generation_cost: Decimal | None
    judge_calls: int
    judge_cost: Decimal | None
    total_cost: Decimal | None
    price_known: bool
    models: list[ModelEstimate]


class ModelProgress(BaseModel):
    model_profile_id: uuid.UUID
    model: str
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0
    cost: Decimal = Decimal(0)


class ExperimentOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    status: ExperimentStatus
    origin: ExperimentOrigin
    prompt_version_id: uuid.UUID
    dataset_version_id: uuid.UUID
    evaluator_set_version_id: uuid.UUID
    split_scope: SplitScope
    config: dict[str, Any]
    estimate: dict[str, Any] | None
    budget_cap: Decimal | None
    total_calls: int
    stop_reason: str | None
    progress: list[ModelProgress]
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class TestCaseRunOut(BaseModel):
    __test__ = False
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    experiment_id: uuid.UUID
    dataset_item_id: uuid.UUID
    prompt_version_id: uuid.UUID
    model_profile_id: uuid.UUID
    provider: str
    model: str
    param_set_key: str
    params: dict[str, Any]
    run_number: int
    status: RunStatus
    rendered_system_prompt: str | None
    rendered_user_prompt: str | None
    raw_output: str | None
    parsed_output: dict[str, Any] | None
    finish_reason: str | None
    error_type: str | None
    error_message: str | None
    attempts: int
    input_tokens: int | None
    output_tokens: int | None
    cost: Decimal | None
    latency_ms: int | None
    ttft_ms: int | None
    llm_call_id: uuid.UUID | None
    started_at: datetime | None
    completed_at: datetime | None
    trace_id: str | None
    span_id: str | None
