"""
Pure improvement logic (DEVELOPMENT.md 5.2-5.4, base level). No I/O.

- `rule_tag` gives a failed case a free, rule-based tag from its output and the evaluators
  it failed: call_error, empty, refusal, format_broken, wrong_label, too_long, or
  low_quality when only a judge marked it down.
- `prompt_diff` is the unified diff between two prompt versions, shown on each candidate.
- `best` picks the candidate with the highest optimize-split quality.
- `verdict` compares the best candidate with the current prompt on the holdout split with the
  significance engine: proven better only for a clear difference on enough cases.
"""

import difflib
import re

from app.modules.assistant.schemas import Reason
from app.modules.evaluation.significance import Comparison, Label

CALL_ERROR = "call_error"
REFUSAL = re.compile(r"\b(i can(?:no|')t|i'm sorry|i am sorry|as an ai|i won't|unable to help)\b", re.I)
FORMAT_EVALUATORS = {"json_valid", "json_schema", "allowed_values", "constraints"}
LABEL_EVALUATORS = {"exact_match", "field_match"}
BETTER = (
    "Proven better: the best candidate beat the current prompt on {cases} held-back cases by {delta:+.0%} quality "
    "(the {level:.0%} interval is {low:+.0%} to {high:+.0%})."
)
WORSE = (
    "The best candidate is clearly worse than the current prompt on the held-back cases ({delta:+.0%} quality), "
    "so keep the current version."
)
NOT_PROVEN = (
    "Not proven: the best candidate scored {delta:+.0%} quality against the current prompt on {cases} held-back "
    "cases, but that is within chance (the {level:.0%} interval is {low:+.0%} to {high:+.0%}). "
    "Keep the current version, or add test cases and improve again."
)
TOO_FEW = (
    "Not proven: only {cases} held-back cases were judged for both prompts, and at least {minimum} are needed to "
    "tell a real improvement from chance{best}. Add more test cases, then improve again."
)
DIFFERENT_JUDGE = (
    "The candidate and the current prompt were scored with different checks or a different judge, "
    "so their scores can't be compared. Score both the same way and try again."
)
UNJUDGED = (
    "Some of the cases could not be judged, so there is no fair comparison to prove an improvement with. "
    "Use Score again on the experiments, then improve again."
)


def rule_tag(output: str | None, failed: set[str]) -> str:
    if CALL_ERROR in failed:
        return CALL_ERROR
    if not (output or "").strip():
        return "empty"
    if REFUSAL.search(output or ""):
        return "refusal"
    if failed & FORMAT_EVALUATORS:
        return "format_broken"
    if failed & LABEL_EVALUATORS:
        return "wrong_label"
    if "length" in failed:
        return "too_long"
    return "low_quality"


def render_prompt(system_template: str | None, user_template: str | None) -> list[str]:
    lines = []
    if system_template:
        lines += ["[system]", *system_template.splitlines()]
    if user_template:
        lines += ["[user]", *user_template.splitlines()]
    return lines


def prompt_diff(old: tuple[str | None, str | None], new: tuple[str | None, str | None]) -> str:
    diff = difflib.unified_diff(render_prompt(*old), render_prompt(*new), "current", "candidate", lineterm="")
    return "\n".join(diff)


def best(qualities: dict[str, float | None]) -> str | None:
    scored = {key: value for key, value in qualities.items() if value is not None}
    return max(scored, key=lambda key: scored[key]) if scored else None


def verdict(found: Comparison, minimum: int) -> tuple[Reason, str]:
    """Is the best candidate proven better than the current prompt on the holdout cases? Only a clear difference
    on at least `minimum` cases judged on both sides says so: a positive difference that could be chance, or
    too few cases to tell, is "not proven" and never lets the candidate be accepted."""
    delta = found.difference
    if found.cases < minimum or delta is None:
        shown = f" (best difference {delta:+.0%})" if delta is not None else ""
        return Reason.TOO_FEW_CASES, TOO_FEW.format(cases=found.cases, minimum=minimum, best=shown)
    low, high = found.low or 0.0, found.high or 0.0
    numbers = {"cases": found.cases, "delta": delta, "level": found.level, "low": low, "high": high}
    if found.label is Label.CLEAR and found.first_better:
        return Reason.PROVEN, BETTER.format(**numbers)
    if found.label is Label.CLEAR:
        return Reason.WORSE, WORSE.format(**numbers)
    return Reason.NOT_PROVEN, NOT_PROVEN.format(**numbers)
