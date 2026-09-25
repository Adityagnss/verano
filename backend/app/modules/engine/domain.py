"""
Experiment lifecycle state machine.

The single source of truth for which status changes are legal (ENGINEERING_STANDARDS 3.3,
DEVELOPMENT.md 1.1). `ensure_transition` is the only check; the engine service's
`transition()` calls it and then applies the change with a compare-and-set UPDATE, so
two processes can never both move an experiment out of the same state. Terminal states
have no outgoing transitions. A rescore never goes through here: it creates a new
EvaluationRun and leaves the experiment's status untouched (ADR 0004).
"""

from app.core.errors import InvalidTransition
from app.modules.engine.schemas import ExperimentStatus as Status

TRANSITIONS: dict[Status, frozenset[Status]] = {
    Status.DRAFT: frozenset({Status.PLANNED}),
    Status.PLANNED: frozenset({Status.RUNNING, Status.CANCELLED}),
    Status.RUNNING: frozenset({Status.EVALUATING, Status.PAUSED, Status.CANCELLED, Status.FAILED}),
    Status.PAUSED: frozenset({Status.RUNNING, Status.CANCELLED}),
    Status.EVALUATING: frozenset({Status.COMPLETED, Status.FAILED}),
    Status.COMPLETED: frozenset(),
    Status.CANCELLED: frozenset(),
    Status.FAILED: frozenset(),
}

TERMINAL: frozenset[Status] = frozenset(status for status, targets in TRANSITIONS.items() if not targets)


def ensure_transition(current: Status, target: Status) -> None:
    if target not in TRANSITIONS[current]:
        allowed = sorted(TRANSITIONS[current])
        raise InvalidTransition(
            f"An experiment that is {current.value} can't become {target.value}.",
            {"current": current.value, "target": target.value, "allowed": allowed},
        )
