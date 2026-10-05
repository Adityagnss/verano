"""Unit tests for what the judge is asked: criteria or steps, the case's own rubric, and the size check."""

import pytest

from app.core.errors import ValidationFailed
from app.modules.evaluation.domain import EvalCase, check_instructions_fit, judge_calls_per_answer
from app.modules.evaluation.plugins.deepeval_adapter import instructions_for
from app.modules.generator.schemas import TaskSpec

SPEC = TaskSpec(
    task_type="classification", goal="Label it", input_variables=[], output_format="single_label", allowed_outputs=["a"]
)


def case(rubric: list[str] | None) -> EvalCase:
    return EvalCase(inputs={}, output="x", expected=None, rubric=rubric, task_spec=SPEC)


def test_criteria_are_used_as_written_and_empty_ones_do_not_apply() -> None:
    assert instructions_for({"criteria": " Be right. "}, case(None)) == ("Be right.", [])
    assert instructions_for({"criteria": "   "}, case(None)) is None
    assert instructions_for({}, case(None)) is None


def test_the_case_rubric_stands_in_for_the_placeholder_and_a_case_without_one_is_not_judged() -> None:
    asked = instructions_for({"criteria": "{rubric}"}, case(["short", "polite"]))
    assert asked is not None
    assert asked[0] == "A good answer meets every one of these criteria: short; polite"
    assert instructions_for({"criteria": "{rubric}"}, case(None)) is None
    assert instructions_for({"criteria": "{rubric}"}, case([])) is None


def test_steps_replace_criteria_and_may_hold_the_rubric_as_one_step() -> None:
    assert instructions_for({"criteria": "ignored", "evaluation_steps": ["a", " b "]}, case(None)) == (None, ["a", "b"])
    asked = instructions_for({"evaluation_steps": ["first", "{rubric}"]}, case(["short"]))
    assert asked == (None, ["first", "A good answer meets every one of these criteria: short"])
    assert instructions_for({"evaluation_steps": ["first", "{rubric}"]}, case(None)) is None


def test_criteria_cost_two_judge_calls_and_steps_one() -> None:
    checks: list[dict[str, object]] = [
        {"kind": "deepeval", "criteria": "x"},
        {"kind": "deepeval", "evaluation_steps": ["a"]},
        {"kind": "rule"},
    ]
    assert judge_calls_per_answer(checks) == 3
    assert judge_calls_per_answer([]) == 0


def test_instructions_that_would_fill_the_judges_window_are_refused_and_unknown_windows_are_not_checked() -> None:
    long = [{"criteria": "x" * 4000}]
    check_instructions_fit(long, None)
    check_instructions_fit(long, 128_000)
    with pytest.raises(ValidationFailed, match="too long for this judge"):
        check_instructions_fit(long, 1_500)
