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
    tool_calls: list[dict[str, Any]] = field(default_factory=list)  # what an app reported: {name, arguments}
    prompt: str | None = None  # the prompt under test, shown to the judges as context (ADR 0038)
    category: str | None = None  # the test case's category (a security check can apply to some categories only)
    reference_on: bool = True  # whether the expected answer may be given to the judges as their reference


def inputs_text(inputs: dict[str, Any]) -> str:
    """What the case sent, as a person or a judge reads it. A file row's text is the message itself, so it is shown
    without its `attachment:` label (the label is Verano's, not part of the customer's message)."""
    if set(inputs) == {"attachment"}:
        return str(inputs["attachment"])
    return "\n".join(f"{key}: {value}" for key, value in inputs.items())


def judge_plan(checks: list[dict[str, Any]], fast: bool, min_checks: int, max_checks: int) -> tuple[int, int]:
    """(judge calls, judged checks) per answer. Accurate scoring is one call per check, or two for a check made of
    criteria. Fast scoring puts the judged checks of an answer into combined calls (one per `max_checks`) when there
    are at least `min_checks` of them; each check is still read once, so the second number is what the cost of
    reading the instructions grows with."""
    judged = sum(1 for check in checks if check.get("kind") == "deepeval")
    if fast and judged >= max(min_checks, 2):
        return -(-judged // max(max_checks, 1)), judged
    calls = judge_calls_per_answer(checks)
    return calls, calls


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
STRONGEST = (
    "{model} is the lowest-priced model not being tested that costs at least as much as the models you test "
    "(a rough sign it is as capable), and it can read as much as they can."
)
NOTHING_STRONGER = (
    "{model} is not being tested and can read as much as the models you test; no model of at least their price "
    "was found, so it may be weaker than them."
)


@dataclass(frozen=True)
class JudgeCandidate:
    credential_id: Any
    model: str
    under_test: bool
    output_price: float | None
    context_window: int | None = None


def suggest_judge(profiles: list[JudgeCandidate]) -> tuple[JudgeCandidate | None, str]:
    """A priced model not under test that can read at least as much as every model under test (the judge
    reads the case and the answer), and of those the cheapest that costs at least as much as the dearest
    model under test (price is a rough proxy for capability). Never simply the most expensive model: that
    can be a legacy model at many times the price with a small context window. A model under test only
    when nothing else exists. The user decides."""
    tested = [p for p in profiles if p.under_test]
    floor_price = max((p.output_price or 0 for p in tested), default=0.0)
    windows = [p.context_window for p in tested if p.context_window]
    needed = min(windows) if windows else 0
    free = [
        p for p in profiles if not p.under_test and p.output_price is not None and (p.context_window or 0) >= needed
    ]
    stronger = [p for p in free if (p.output_price or 0) >= floor_price]
    if stronger:
        best = min(stronger, key=lambda p: (p.output_price or 0, p.model))
        return best, STRONGEST.format(model=best.model)
    if free:
        best = max(free, key=lambda p: (p.output_price or 0, p.model))
        return best, NOTHING_STRONGER.format(model=best.model)
    priced = [p for p in profiles if p.output_price is not None]
    if priced:
        return max(priced, key=lambda p: p.output_price or 0), NO_OTHER
    return None, NO_OTHER
