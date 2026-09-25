"""Evaluation enums: evaluation-run lifecycle and what triggered a run."""

from enum import StrEnum


class EvaluationRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class EvaluationTrigger(StrEnum):
    INITIAL = "initial"
    RESCORE = "rescore"
