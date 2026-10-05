"""
The Evaluator contract (DEVELOPMENT.md 1.1).

Every evaluator, whether one of our rule checks, the DeepEval adapter or a future Ragas /
custom / human evaluator, implements `Evaluator.evaluate(case) -> Score`. Scores are
always normalized to 0.0-1.0 and `passed` is decided against the evaluator's threshold,
so combining scores across evaluators is uniform. Pure types; no I/O.
"""

from dataclasses import dataclass, field
from typing import Any, ClassVar, Protocol

from app.modules.generator.schemas import TaskSpec


@dataclass(frozen=True)
class EvalCase:
    inputs: dict[str, Any]
    output: str
    expected: str | None
    rubric: list[str] | None
    task_spec: TaskSpec
    context: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Score:
    value: float
    passed: bool
    reason: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0.0 <= self.value <= 1.0:
            raise ValueError(f"score value must be within 0.0-1.0, got {self.value}")


@dataclass(frozen=True)
class Unscored:
    """An evaluator that applies to a case but could not produce a score (the judge failed or is missing).
    Never a pass and never a zero: the case is left out of the numbers and shown as unscored."""

    reason: str


class Evaluator(Protocol):
    name: ClassVar[str]
    version: ClassVar[str]

    async def evaluate(self, case: EvalCase) -> Score: ...


def score(value: float, threshold: float, reason: str, **metadata: Any) -> Score:
    return Score(value=value, passed=value >= threshold, reason=reason, metadata=metadata)
