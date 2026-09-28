"""
Experiment lifecycle state machine.

The single source of truth for which status changes are legal (ENGINEERING_STANDARDS 3.3,
DEVELOPMENT.md 1.1). `ensure_transition` is the only check; the engine service's
`transition()` calls it and then applies the change with a compare-and-set UPDATE, so
two processes can never both move an experiment out of the same state. Terminal states
have no outgoing transitions. A rescore never goes through here: it creates a new
EvaluationRun and leaves the experiment's status untouched (ADR 0004).

Also the pure matrix planner (DEVELOPMENT.md 3.2): one planned call per item × model ×
parameter set × run, each with a deterministic id; chunking; and output parsing.
"""

import contextlib
import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Any

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


RUN_NAMESPACE = uuid.UUID("5b3a4f1e-7c2d-4e8a-9f60-1d2c3b4a5e6f")


@dataclass(frozen=True)
class PlannedCall:
    id: uuid.UUID
    dataset_item_id: uuid.UUID
    model_profile_id: uuid.UUID
    param_set_key: str
    params: dict[str, Any]
    run_number: int


def param_set_key(params: dict[str, Any]) -> str:
    """A short stable name for one parameter set, the same for equal parameters."""
    payload = json.dumps(params, sort_keys=True, default=str)
    return hashlib.blake2b(payload.encode(), digest_size=6).hexdigest()


def run_id(experiment_id: uuid.UUID, item_id: uuid.UUID, model_id: uuid.UUID, key: str, run: int) -> uuid.UUID:
    """Deterministic id per matrix cell, so planning or retrying twice never duplicates a call."""
    return uuid.uuid5(RUN_NAMESPACE, f"{experiment_id}:{item_id}:{model_id}:{key}:{run}")


def plan_matrix(
    experiment_id: uuid.UUID, item_ids: list[uuid.UUID], models: list[tuple[uuid.UUID, int, dict[str, Any]]]
) -> list[PlannedCall]:
    """total calls = Σ per model (items × 1 param set × runs)."""
    calls = []
    for model_id, runs, params in models:
        key = param_set_key(params)
        for item_id in item_ids:
            for run in range(1, runs + 1):
                calls.append(
                    PlannedCall(run_id(experiment_id, item_id, model_id, key, run), item_id, model_id, key, params, run)
                )
    return calls


def chunks(ids: list[uuid.UUID], size: int) -> list[list[uuid.UUID]]:
    return [ids[start : start + size] for start in range(0, len(ids), size)]


def parse_output(text: str) -> dict[str, Any]:
    """The parsed form of a reply: its JSON value when it is JSON, always its stripped text."""
    stripped = text.strip()
    parsed: dict[str, Any] = {"text": stripped}
    with contextlib.suppress(ValueError):
        parsed["json"] = json.loads(stripped)
    return parsed
