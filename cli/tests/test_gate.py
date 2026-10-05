"""The quality gate: exactly where it passes and fails, per model."""

from typing import Any

import pytest

from verano.gate import evaluate
from verano.spec import Gate


def model(name: str, quality: float, passed: float | None = None) -> dict[str, Any]:
    return {"model": name, "quality": quality, "pass_rate": quality if passed is None else passed}


def test_a_score_equal_to_the_minimum_passes_and_just_below_fails() -> None:
    gate = Gate(min_quality=0.8, min_pass_rate=0.7)
    assert evaluate(gate, [model("a", 0.8, 0.7)], True, None, None).passed
    below = evaluate(gate, [model("a", 0.79, 0.69)], True, None, None)
    assert [f.split(":")[0] for f in below.failures] == ["a", "a"]


def test_every_model_is_judged_on_its_own() -> None:
    gate = Gate(min_quality=0.8)
    verdict = evaluate(gate, [model("strong", 0.95), model("weak", 0.5)], True, None, None)
    assert verdict.failures == ["weak: quality 50% is below the minimum 80%."]


def test_a_drop_of_exactly_the_allowed_size_passes_despite_rounding() -> None:
    gate = Gate(max_drop=0.1)
    assert evaluate(gate, [model("a", 0.7)], True, None, {"a": 0.8}).passed
    assert not evaluate(gate, [model("a", 0.69)], True, None, {"a": 0.8}).passed
    assert evaluate(gate, [model("a", 0.9)], True, None, {"a": 0.8}).passed


def test_no_baseline_is_a_note_and_a_model_missing_from_it_is_too() -> None:
    gate = Gate(max_drop=0.05)
    first = evaluate(gate, [model("a", 0.1)], True, None, None)
    assert first.passed
    assert first.notes == ["a: no earlier run to compare with, so the drop was not checked."]
    new_model = evaluate(gate, [model("a", 0.1), model("b", 0.1)], True, None, {"a": 0.1})
    assert new_model.passed
    assert len(new_model.notes) == 1


def test_a_run_that_did_not_finish_never_passes() -> None:
    verdict = evaluate(Gate(min_quality=0.0), [model("a", 1.0)], False, "Cancelled by the user.", None)
    assert verdict.failures == ["The run stopped early (Cancelled by the user), so its scores can't be trusted."]
    assert (
        evaluate(Gate(min_quality=0.0), [model("a", 1.0)], False, None, None)
        .failures[0]
        .startswith("The run stopped early, so")
    )


@pytest.mark.parametrize("bad", [{}, {"min_quality": 1.5}, {"max_drop": -0.1}, {"min_pass_rate": "high"}])
def test_a_gate_must_check_something_with_scores_between_zero_and_one(bad: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="validation error"):
        Gate(**bad)


def test_answers_the_judge_could_not_score_fail_the_gate_even_when_the_rest_looks_good() -> None:
    gate = Gate(min_quality=0.5)
    flattered = {**model("a", 0.9), "unscored_cases": 4, "cases": 10, "judged_cases": 6}
    verdict = evaluate(gate, [flattered], True, None, None)
    assert verdict.failures == ["a: 4 answers could not be judged, so its scores can't be trusted."]


def test_a_model_with_nothing_judged_has_no_score_to_compare_and_fails() -> None:
    gate = Gate(min_quality=0.5, max_drop=0.1)
    nothing = {"model": "a", "quality": None, "pass_rate": None, "cases": 5, "judged_cases": 0, "unscored_cases": 5}
    assert evaluate(gate, [nothing], True, None, {"a": 0.8}).failures == [
        "a: 5 answers could not be judged, so its scores can't be trusted."
    ]
    silent = {**nothing, "unscored_cases": 0}
    assert evaluate(gate, [silent], True, None, None).failures == ["a: nothing could be scored."]
