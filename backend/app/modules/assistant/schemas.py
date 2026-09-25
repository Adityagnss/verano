"""Assistant enums: optimization session and candidate outcomes."""

from enum import StrEnum


class OptimizationStatus(StrEnum):
    ACTIVE = "active"
    CLOSED = "closed"


class CandidateOutcome(StrEnum):
    PENDING = "pending"
    BETTER = "better"
    NOT_BETTER = "not_better"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
