"""
Sandbox contract.

Pydantic models shared by the runner, the worker, the HTTP service and its client, plus the pure
function that turns whatever a user's `check(case)` returned into (score, passed, reason).
Imported by every other file in this package; it imports nothing from the rest of the app.
A check returns a float 0..1, a bool, a (score, reason) tuple or a dict with score/passed/reason.
"""

import math
from typing import Any

from pydantic import BaseModel, Field

PASS_SCORE = 0.5


class SandboxLimits(BaseModel):
    wall_s: float
    cpu_s: int
    memory_mb: int
    output_chars: int


class SandboxRequest(BaseModel):
    code: str
    case: dict[str, Any] = Field(description="Keys: inputs, output, expected, rubric.")


class SandboxResult(BaseModel):
    ok: bool
    score: float | None = Field(default=None, ge=0, le=1)
    passed: bool | None = None
    reason: str = ""
    error: str | None = None
    timed_out: bool = False


def _as_score(value: object) -> float:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, int | float) and math.isfinite(value) and 0 <= value <= 1:
        return float(value)
    raise ValueError("a score must be a number from 0 to 1")


def _as_reason(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    raise ValueError("a reason must be text")


def _from_dict(value: dict[Any, Any]) -> tuple[float, bool, str]:
    reason = _as_reason(value.get("reason"))
    passed = value.get("passed")
    if passed is not None and not isinstance(passed, bool):
        raise ValueError("'passed' must be true or false")
    if "score" in value:
        score = _as_score(value["score"])
        return score, score >= PASS_SCORE if passed is None else passed, reason
    if passed is None:
        raise ValueError("a result dict needs 'score' or 'passed'")
    return (1.0 if passed else 0.0), passed, reason


def normalise_result(value: object) -> tuple[float, bool, str]:
    if isinstance(value, dict):
        return _from_dict(value)
    if isinstance(value, tuple) and len(value) == 2:
        score = _as_score(value[0])
        return score, score >= PASS_SCORE, _as_reason(value[1])
    if isinstance(value, bool | int | float):
        score = _as_score(value)
        return score, score >= PASS_SCORE, ""
    raise ValueError("check must return a score, a bool, a (score, reason) tuple or a dict")
