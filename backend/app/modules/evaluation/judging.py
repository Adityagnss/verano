"""
What a judge is told, and how several checks share one judge call (ADR 0038). Pure code, no I/O.

- The prompt under test is given to the judge as context, so it knows what the model was asked to do.
- A case's expected answer is the judge's reference ("a good answer agrees with it in substance") unless the
  check opts out with `use_reference: false`.
- A combined call scores several judged checks of one answer in one structured reply; a check the reply does not
  answer properly is scored again by a call of its own, never guessed.
- A rubric (a list of criteria) is checked for criteria the judge cannot answer, that are vague or that
  contradict each other, before it is trusted.
"""

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from app.modules.evaluation.domain import EvalCase, Score, inputs_text, score

REFERENCE_NOTE = (
    "The expected output is a reference answer: a good answer agrees with it in substance, "
    "even when the wording differs."
)
REFERENCE_STEP = "Compare the answer with the expected output: it should agree in substance, not in wording."
SCORE_SCALE = 10.0
NO_REASON = "The judge gave no reason."


def prompt_text(system: str | None, user: str | None, max_chars: int) -> str | None:
    """The prompt the model under test was sent, for the judge to read; None when there is nothing to show or
    `max_chars` is 0 (the setting is off). A long prompt is cut with a plain marker, never silently."""
    if max_chars <= 0 or not ((system or "").strip() or (user or "").strip()):
        return None
    parts = []
    if system and system.strip():
        parts.append(f"System message:\n{system.strip()}")
    if user and user.strip():
        parts.append(f"User message:\n{user.strip()}")
    text = "\n\n".join(parts)
    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + "\n[the rest of the prompt was left out because it is long]"
    return text


def sees_prompt(config: dict[str, Any], case: EvalCase) -> bool:
    return bool(case.prompt) and config.get("include_prompt") is not False


def reference_of(config: dict[str, Any], case: EvalCase) -> str | None:
    """The golden answer given to the judge as its reference, or None. A check that needs the expected answer
    always gets it; any other check can opt out with `use_reference: false`, and the server can switch it off."""
    if not case.expected:
        return None
    needs = {part.strip() for part in str(config.get("requires") or "").split(",")}
    if "expected" in needs:
        return case.expected
    if not case.reference_on or config.get("use_reference") is False:
        return None
    return case.expected


def input_for_judge(config: dict[str, Any], case: EvalCase) -> str:
    """The case as the judge reads it: the prompt under test (when shown), then what the case sent."""
    sent = inputs_text(case.inputs)
    if not sees_prompt(config, case):
        return sent
    return f"The prompt the model was given:\n{case.prompt}\n\nWhat this case sent:\n{sent}"


def with_reference_note(criteria: str | None, steps: list[str], reference_used: bool) -> tuple[str | None, list[str]]:
    """Adds the reference sentence to the instructions when a reference is used (a step when steps are given)."""
    if not reference_used:
        return criteria, steps
    if steps:
        return criteria, [*steps, REFERENCE_STEP]
    if not criteria:
        return REFERENCE_NOTE, steps
    stop = "" if criteria.rstrip().endswith((".", "!", "?", ":")) else "."
    return f"{criteria.rstrip()}{stop} {REFERENCE_NOTE}", steps


def cache_extras(config: dict[str, Any], case: EvalCase) -> dict[str, Any]:
    """What a stored judge result must also depend on: the prompt shown and whether a reference was used. Empty
    when neither applies, so earlier keys stay valid."""
    extras: dict[str, Any] = {}
    if sees_prompt(config, case):
        extras["prompt"] = case.prompt
    if case.expected:
        extras["reference"] = reference_of(config, case) is not None
    return extras


# ---------------------------------------------------------------------------------------------------------------
# The combined judge call


class CheckVerdict(BaseModel):
    name: str
    score: float = Field(description="0 (fails completely) to 10 (fully meets it)")
    reason: str = ""


class CombinedVerdicts(BaseModel):
    checks: list[CheckVerdict]


@dataclass(frozen=True)
class CombinedCheck:
    name: str
    threshold: float
    criteria: str | None
    steps: list[str]
    config: dict[str, Any]


COMBINED_INTRO = (
    "You are judging one answer against several separate checks. Judge every check on its own, using only its "
    "own wording. Score each from 0 (fails completely) to 10 (fully meets it) and give a short reason that "
    "points at the answer. Reply with JSON only."
)
COMBINED_SHAPE = 'Reply as {"checks": [{"name": "<the check name exactly>", "score": <0-10>, "reason": "<why>"}]}.'


def combined_prompt(checks: Sequence[CombinedCheck], case: EvalCase, answer: str) -> str:
    """One prompt for several checks of one answer. Each check's text is exactly what it would be alone."""
    anyone_sees_prompt = any(sees_prompt(c.config, case) for c in checks)
    sections = [COMBINED_INTRO]
    if anyone_sees_prompt:
        sections.append(f"The prompt the model was given:\n{case.prompt}")
    sections.append(f"What this case sent:\n{inputs_text(case.inputs)}")
    if any(reference_of(c.config, case) is not None for c in checks):
        sections.append(f"Reference answer (the expected output):\n{case.expected}")
    if case.context and any(str(c.config.get("requires") or "").find("context") >= 0 for c in checks):
        sections.append("Context the answer may rely on:\n" + "\n".join(f"- {item}" for item in case.context))
    sections.append(f"The answer to judge:\n{answer}")
    listed = []
    for number, check in enumerate(checks, start=1):
        used = reference_of(check.config, case) is not None
        criteria, steps = with_reference_note(check.criteria, check.steps, used)
        body = (
            f"Criteria: {criteria}"
            if not steps
            else "Steps:\n" + "\n".join(f"  {n}. {s}" for n, s in enumerate(steps, 1))
        )
        if steps and criteria:
            body = f"Criteria: {criteria}\n{body}"
        listed.append(f"Check {number}, named {json.dumps(check.name)}:\n{body}")
    sections.append("The checks:\n\n" + "\n\n".join(listed))
    sections.append(COMBINED_SHAPE)
    return "\n\n".join(sections)


def read_combined(checks: Sequence[CombinedCheck], reply: CombinedVerdicts) -> dict[str, Score | None]:
    """Each check's score from the reply, or None for a check the reply left out, repeated or scored outside
    0 to 10: those are scored again separately by the caller."""
    wanted = {c.name: c for c in checks}
    seen: dict[str, list[CheckVerdict]] = {}
    for verdict in reply.checks:
        seen.setdefault(verdict.name.strip(), []).append(verdict)
    found: dict[str, Score | None] = {}
    for name, check in wanted.items():
        verdicts = seen.get(name, [])
        if len(verdicts) != 1 or not 0.0 <= verdicts[0].score <= SCORE_SCALE:
            found[name] = None
            continue
        value = verdicts[0].score / SCORE_SCALE
        found[name] = score(value, check.threshold, verdicts[0].reason.strip() or NO_REASON, combined=True)
    return found


def share_of(total: float, count: int) -> float:
    """One check's equal share of a combined call's tokens or cost."""
    return total / count if count else 0.0


# ---------------------------------------------------------------------------------------------------------------
# The rubric self-check

VAGUE_WORDS = ("good", "nice", "great", "appropriate", "proper", "quality", "better", "well", "correct", "fine")
NOT_ANSWERABLE = "not_answerable"
VAGUE = "vague"
INCONSISTENT = "inconsistent"
DUPLICATE = "duplicate"
SIZE = "size"


class RubricIssue(BaseModel):
    kind: str  # not_answerable, vague, inconsistent, duplicate or size
    criterion: int | None = None  # 1-based position of the criterion, when one is at fault
    detail: str
    suggestion: str | None = None


class RubricReview(BaseModel):
    """What the judge said when asked to read a rubric critically (the reply it must return)."""

    issues: list[RubricIssue] = []


class GeneratedCriteria(BaseModel):
    """What the judge must return when asked to write criteria."""

    criteria: list[str]


def clean_criteria(criteria: Sequence[str], max_chars: int) -> list[str]:
    """Trimmed, de-duplicated (ignoring case) and cut to a sane length, in the original order."""
    seen: set[str] = set()
    cleaned = []
    for raw in criteria:
        text = re.sub(r"\s+", " ", str(raw)).strip().lstrip("-*0123456789. ").strip()
        if not text or text.lower() in seen:
            continue
        seen.add(text.lower())
        cleaned.append(text[:max_chars])
    return cleaned


def local_issues(criteria: Sequence[str], minimum: int, maximum: int, max_chars: int) -> list[RubricIssue]:
    """Problems found without asking a model: too few or too many criteria, repeats, text too long, and
    criteria that are only a vague word ("be good") with nothing to look for in the answer."""
    found: list[RubricIssue] = []
    if len(criteria) < minimum:
        found.append(
            RubricIssue(
                kind=SIZE, detail=f"Only {len(criteria)} criteria; {minimum} to {maximum} cover an answer well."
            )
        )
    if len(criteria) > maximum:
        found.append(
            RubricIssue(
                kind=SIZE, detail=f"{len(criteria)} criteria is a lot; a judge scores long lists less carefully."
            )
        )
    seen: dict[str, int] = {}
    for number, text in enumerate(criteria, start=1):
        key = re.sub(r"\W+", " ", text.lower()).strip()
        if key in seen:
            found.append(
                RubricIssue(kind=DUPLICATE, criterion=number, detail=f"Says the same as criterion {seen[key]}.")
            )
        seen.setdefault(key, number)
        if len(text) > max_chars:
            found.append(RubricIssue(kind=SIZE, criterion=number, detail=f"Longer than {max_chars} characters."))
        words = re.findall(r"[a-z']+", text.lower())
        if len(words) <= 4 and any(word in VAGUE_WORDS for word in words):
            found.append(
                RubricIssue(
                    kind=VAGUE,
                    criterion=number,
                    detail="Names a quality without saying what to look for in the answer.",
                    suggestion="Say what the answer must contain or avoid.",
                )
            )
    return found


WRITE_INTRO = (
    "You write the criteria a judge uses to decide whether an answer is good. Each criterion must be one short "
    "sentence that can be decided by reading the answer (and the reference answer, when there is one), name "
    "something observable, and not overlap or contradict another. Do not write criteria that need facts "
    "the judge cannot see."
)


def write_prompt(
    goal: str, prompt: str | None, rules: Sequence[str], risks: Sequence[str], count: int, focus: str | None
) -> str:
    sections = [WRITE_INTRO, f"What the task is for: {goal}"]
    if prompt:
        sections.append(f"The prompt the model is given:\n{prompt}")
    if rules:
        sections.append("Rules the task states:\n" + "\n".join(f"- {r}" for r in rules))
    if risks:
        sections.append("Where it tends to go wrong:\n" + "\n".join(f"- {r}" for r in risks))
    if focus and focus.strip():
        sections.append(f"Pay particular attention to: {focus.strip()}")
    sections.append(f'Write {count} criteria. Reply as {{"criteria": ["...", "..."]}}.')
    return "\n\n".join(sections)


CHECK_INTRO = (
    "You review a rubric before it is used to judge answers. For each criterion decide: can a judge answer it "
    "from the case, the answer and the reference alone (not_answerable if it needs outside facts or the "
    "model's hidden state); is it specific enough that two judges would agree (vague if not); and do any "
    "criteria contradict each other (inconsistent). Report only real problems, with the criterion's number."
)


def check_prompt(criteria: Sequence[str], goal: str | None, prompt: str | None) -> str:
    sections = [CHECK_INTRO]
    if goal:
        sections.append(f"What the task is for: {goal}")
    if prompt:
        sections.append(f"The prompt the model is given:\n{prompt}")
    sections.append("The rubric:\n" + "\n".join(f"{n}. {text}" for n, text in enumerate(criteria, start=1)))
    sections.append(
        'Reply as {"issues": [{"kind": "not_answerable|vague|inconsistent", "criterion": <number or null>, '
        '"detail": "<what is wrong>", "suggestion": "<a better wording>"}]}. '
        'Reply {"issues": []} if the rubric is sound.'
    )
    return "\n\n".join(sections)


KINDS = {NOT_ANSWERABLE, VAGUE, INCONSISTENT}


def trusted_issues(reply: RubricReview, count: int) -> list[RubricIssue]:
    """The judge's issues that make sense: a known kind, and a criterion number that exists (or none)."""
    kept = []
    for issue in reply.issues:
        if issue.kind not in KINDS:
            continue
        if issue.criterion is not None and not 1 <= issue.criterion <= count:
            issue = issue.model_copy(update={"criterion": None})
        kept.append(issue)
    return kept
