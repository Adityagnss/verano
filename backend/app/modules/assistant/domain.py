"""
Pure improvement logic (DEVELOPMENT.md 5.2-5.4, base level). No I/O.

- `rule_tag` gives a failed case a free, rule-based tag from its output and the evaluators
  it failed: call_error, empty, refusal, format_broken, wrong_label, too_long, or
  low_quality when only a judge marked it down.
- `prompt_diff` is the unified diff between two prompt versions, shown on each candidate.
- `best` picks the candidate with the highest optimize-split quality.
- `verdict` compares the best candidate with the current prompt on the holdout split:
  better only when its holdout quality is strictly higher (plain difference at base level).
"""

import difflib
import re

CALL_ERROR = "call_error"
REFUSAL = re.compile(r"\b(i can(?:no|')t|i'm sorry|i am sorry|as an ai|i won't|unable to help)\b", re.I)
FORMAT_EVALUATORS = {"json_valid", "json_schema", "allowed_values", "constraints"}
LABEL_EVALUATORS = {"exact_match", "field_match"}
BETTER = "The best candidate beat the current prompt on the holdout cases by {delta:+.0%} quality."
NOT_BETTER = (
    "No candidate beat the current prompt on the holdout cases (best difference {delta:+.0%}), "
    "so keep the current version."
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


def verdict(candidate: float, baseline: float) -> tuple[bool, str]:
    delta = candidate - baseline
    better = delta > 0
    return better, (BETTER if better else NOT_BETTER).format(delta=delta)
