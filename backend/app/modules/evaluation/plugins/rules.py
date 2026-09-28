"""
Our rule evaluators (DEVELOPMENT.md 2.3 Step E): deterministic, free checks on one output.

- `exact_match`: the output equals the expected output after normalizing case, spaces and
  surrounding punctuation.
- `allowed_values`: the output is one of the Task Spec's allowed labels.
- `json_valid` / `json_schema`: the output is JSON (code fences allowed) / matches the
  Task Spec's output schema.
- `field_match`: share of the expected JSON's top-level fields the output gets right.
- `length`: a summary is shorter than what it summarizes.
- `constraints`: the Task Spec rules that can be checked mechanically ("one word",
  "lowercase", "at most N words / characters"); rules it can't read are listed as
  unchecked in the reason, never guessed.
An evaluator returns None when it doesn't apply to a case (for example no expected output),
so it is left out of that case's score instead of counting as a failure.
"""

import json
import re
from collections.abc import Callable
from typing import Any

import jsonschema

from app.modules.evaluation.domain import EvalCase, Score, score
from app.modules.generator.domain import normalize_label

Rule = Callable[[EvalCase, dict[str, Any], float], Score | None]
RULES: dict[str, Rule] = {}
FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)
WORD_LIMIT = re.compile(r"(?:at most|no more than|max(?:imum)?|under|fewer than)\s+(\d+)\s+words?", re.I)
CHAR_LIMIT = re.compile(r"(?:at most|no more than|max(?:imum)?|under|fewer than)\s+(\d+)\s+(?:characters|chars)", re.I)


def rule(name: str) -> Callable[[Rule], Rule]:
    def register(function: Rule) -> Rule:
        RULES[name] = function
        return function

    return register


def _json(text: str) -> Any:
    return json.loads(FENCE.sub("", text.strip()))


@rule("exact_match")
def exact_match(case: EvalCase, config: dict[str, Any], threshold: float) -> Score | None:
    if case.expected is None:
        return None
    same = normalize_label(case.output) == normalize_label(case.expected)
    return score(
        1.0 if same else 0.0, threshold, "Matches the expected answer." if same else f"Expected '{case.expected}'."
    )


@rule("allowed_values")
def allowed_values(case: EvalCase, config: dict[str, Any], threshold: float) -> Score | None:
    allowed = config.get("allowed_outputs") or case.task_spec.allowed_outputs
    if not allowed:
        return None
    ok = normalize_label(case.output) in {normalize_label(label) for label in allowed}
    return score(1.0 if ok else 0.0, threshold, "An allowed label." if ok else f"Not one of: {', '.join(allowed)}.")


@rule("json_valid")
def json_valid(case: EvalCase, config: dict[str, Any], threshold: float) -> Score:
    try:
        _json(case.output)
    except ValueError as exc:
        return score(0.0, threshold, f"Not valid JSON: {exc}.")
    return score(1.0, threshold, "Valid JSON.")


@rule("json_schema")
def json_schema(case: EvalCase, config: dict[str, Any], threshold: float) -> Score | None:
    schema = config.get("output_schema") or case.task_spec.output_schema
    if not schema:
        return None
    try:
        jsonschema.validate(_json(case.output), schema)
    except (ValueError, jsonschema.ValidationError) as exc:
        return score(0.0, threshold, f"Doesn't match the schema: {str(exc).splitlines()[0]}")
    return score(1.0, threshold, "Matches the schema.")


@rule("field_match")
def field_match(case: EvalCase, config: dict[str, Any], threshold: float) -> Score | None:
    try:
        expected = _json(case.expected or "")
    except ValueError:
        return None
    if not isinstance(expected, dict) or not expected:
        return None
    try:
        output = _json(case.output)
    except ValueError:
        output = {}
    right = [key for key, value in expected.items() if isinstance(output, dict) and output.get(key) == value]
    wrong = sorted(set(expected) - set(right))
    return score(
        len(right) / len(expected),
        threshold,
        f"Wrong or missing: {', '.join(wrong)}." if wrong else "All fields match.",
    )


@rule("length")
def length(case: EvalCase, config: dict[str, Any], threshold: float) -> Score:
    source = sum(len(str(value)) for value in case.inputs.values())
    ok = len(case.output) < source
    return score(1.0 if ok else 0.0, threshold, "Shorter than the input." if ok else "Not shorter than the input.")


def _check(constraint: str, output: str) -> bool | None:
    text = constraint.lower()
    if "one word" in text or "single word" in text:
        return len(output.split()) == 1
    if "lowercase" in text or "lower case" in text:
        return output == output.lower()
    if match := WORD_LIMIT.search(constraint):
        return len(output.split()) <= int(match.group(1))
    if match := CHAR_LIMIT.search(constraint):
        return len(output) <= int(match.group(1))
    return None


@rule("constraints")
def constraints(case: EvalCase, config: dict[str, Any], threshold: float) -> Score | None:
    results = {c: _check(c, case.output.strip()) for c in config.get("constraints") or case.task_spec.constraints}
    checked = {c: ok for c, ok in results.items() if ok is not None}
    if not checked:
        return None
    broken = [c for c, ok in checked.items() if not ok]
    unchecked = [c for c, ok in results.items() if ok is None]
    reason = f"Broke: {'; '.join(broken)}." if broken else "Follows every checkable rule."
    if unchecked:
        reason += f" Not checked automatically: {'; '.join(unchecked)}."
    return score(sum(checked.values()) / len(checked), threshold, reason)
