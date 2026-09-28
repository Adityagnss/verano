"""
Evaluation schemas: evaluation-run lifecycle and trigger, and the versioned evaluator set
(its evaluators, thresholds, weights and editable judge rubrics).
"""

import uuid
from datetime import datetime
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
