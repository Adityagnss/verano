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


def judge_calls_per_answer(checks: list[dict[str, Any]]) -> int:
    """Judge calls one answer needs: a judged check made of criteria first has the judge write its own
    evaluation steps (one call) and then scores (another); a check given its steps scores directly."""
    return sum(1 if check.get("evaluation_steps") else 2 for check in checks if check.get("kind") == "deepeval")


INSTRUCTIONS_TOO_LONG = (
    "The judging instructions are about {tokens} tokens, too long for this judge (it reads {window}) once the "
    "answer is added. Shorten them or choose a judge with a larger context window."
)


def check_instructions_fit(checks: list[dict[str, Any]], context_window: int | None) -> None:
    """Refuses instructions that would take up more than half of the judge's context window, which leaves too
    little room for the question and the answer. Unknown windows are not checked. About 4 characters a token."""
    from app.core.errors import ValidationFailed

    if not context_window:
        return
    chars = sum(
        len(str(c.get("criteria") or "")) + sum(len(str(x)) for x in c.get("evaluation_steps") or []) for c in checks
    )
    tokens = chars // 4
    if tokens > context_window // 2:
        raise ValidationFailed(INSTRUCTIONS_TOO_LONG.format(tokens=tokens, window=context_window))


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


NO_OTHER = "Every model you can reach is also being tested, so the judge will be one of them."
STRONGEST = "{model} is the highest-priced model that is not being tested, a rough sign of the most capable one."


@dataclass(frozen=True)
class JudgeCandidate:
    credential_id: Any
    model: str
    under_test: bool
    output_price: float | None


def suggest_judge(profiles: list[JudgeCandidate]) -> tuple[JudgeCandidate | None, str]:
    """The priced model that is not under test with the highest output price (price is a rough proxy for
    capability); a model under test only when nothing else exists. The user decides."""
    free = [p for p in profiles if not p.under_test and p.output_price is not None]
    if free:
        best = max(free, key=lambda p: p.output_price or 0)
        return best, STRONGEST.format(model=best.model)
    priced = [p for p in profiles if p.output_price is not None]
    if priced:
        return max(priced, key=lambda p: p.output_price or 0), NO_OTHER
    return None, NO_OTHER
