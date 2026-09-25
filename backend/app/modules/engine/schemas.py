"""Engine enums: experiment lifecycle states, per-call run states and split scope."""

from enum import StrEnum


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
