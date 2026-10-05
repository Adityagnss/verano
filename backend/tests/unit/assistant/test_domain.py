"""Unit tests for Improve's pure rules: failure tags, the best candidate and the honest verdict."""

import pytest

from app.modules.assistant.domain import best, prompt_diff, rule_tag, verdict
from app.modules.assistant.schemas import Reason
from app.modules.evaluation.significance import CaseResult, compare

pytestmark = pytest.mark.unit


def test_rule_tags_best_candidate_and_diff() -> None:
    assert rule_tag(None, {"call_error"}) == "call_error"
    assert rule_tag("  ", {"exact_match"}) == "empty"
    assert rule_tag("I'm sorry, I can't help", {"exact_match"}) == "refusal"
    assert rule_tag("Billing!", {"allowed_values", "exact_match"}) == "format_broken"
    assert rule_tag("shipping", {"exact_match"}) == "wrong_label"
    assert best({"a": 0.4, "b": 0.7, "c": None}) == "b"
    assert "+[system]" not in prompt_diff(("Be brief.", None), ("Be brief.", None))
    assert "+Reply with one word." in prompt_diff(("Be brief.", None), ("Be brief.\nReply with one word.", None))


def cases(qualities: list[float]) -> dict[str, CaseResult]:
    return {f"c{i}": CaseResult(q, q >= 0.5) for i, q in enumerate(qualities)}


def test_only_a_clear_difference_on_enough_cases_is_proven() -> None:
    better = compare(cases([0.9] * 40), cases([0.6] * 40), seed=1)
    reason, message = verdict(better, 30)
    assert reason is Reason.PROVEN
    assert "Proven better" in message
    assert "+30%" in message
    assert "40 held-back cases" in message


def test_a_positive_difference_that_could_be_chance_is_not_proven() -> None:
    first = cases([0.5, 0.9, 0.2, 0.7, 0.4, 0.8, 0.3, 0.6] * 5)
    second = cases([0.6, 0.8, 0.3, 0.6, 0.5, 0.7, 0.3, 0.55] * 5)
    reason, message = verdict(compare(first, second, seed=2), 30)
    assert reason is Reason.NOT_PROVEN
    assert message.startswith("Not proven")
    assert "within chance" in message


def test_a_clear_gain_on_too_few_cases_is_still_not_proven() -> None:
    small = compare(cases([0.9] * 20), cases([0.1] * 20), seed=3)
    assert small.label.value == "clear difference"
    reason, message = verdict(small, 30)
    assert reason is Reason.TOO_FEW_CASES
    assert "only 20 held-back cases" in message
    assert "at least 30" in message
    assert "+80%" in message  # the best difference is still shown


def test_a_clearly_worse_candidate_and_no_comparable_cases_are_named() -> None:
    reason, message = verdict(compare(cases([0.2] * 40), cases([0.8] * 40), seed=4), 30)
    assert reason is Reason.WORSE
    assert "clearly worse" in message
    nothing = verdict(compare({}, cases([0.8] * 40), seed=4), 30)
    assert nothing[0] is Reason.TOO_FEW_CASES
    assert "only 0 held-back cases" in nothing[1]
