"""Unit tests for stability: when two answers are the same, agreement per case, and replication."""

import uuid

import pytest

from app.modules.evaluation.stability import Answer, agreement, case_agreements, model_stability, normalize, replication

pytestmark = pytest.mark.unit

MODEL, OTHER = uuid.uuid4(), uuid.uuid4()
CASE_A, CASE_B = uuid.uuid4(), uuid.uuid4()


def answer(model: uuid.UUID, case: uuid.UUID, run: int, text: str) -> Answer:
    return Answer(model, case, run, text)


def test_answers_match_after_whitespace_and_json_formatting_but_nothing_fuzzier() -> None:
    assert normalize("  billing \n") == normalize("billing")
    assert normalize("two   words") == normalize("two words")
    assert normalize('{"a": 1, "b": [1, 2]}') == normalize('{\n "b": [1,2],\n "a": 1}')
    assert normalize("Billing") != normalize("billing")
    assert normalize("1") != normalize("1.0")
    assert normalize("") == ""


def test_agreement_is_the_largest_group_of_matching_answers() -> None:
    assert (agreement(["a", "a", "b", "a", "c"]).same, agreement(["a", "a", "b", "a", "c"]).runs) == (3, 5)
    assert agreement(["a", "b"]).same == 1
    assert agreement(["x", " x "]).same == 2


def test_a_case_needs_two_answers_to_be_compared_and_models_are_kept_apart() -> None:
    answers = [
        answer(MODEL, CASE_A, 1, "x"),
        answer(MODEL, CASE_A, 2, "x"),
        answer(MODEL, CASE_A, 3, "y"),
        answer(MODEL, CASE_B, 1, "z"),
        answer(OTHER, CASE_A, 1, "x"),
        answer(OTHER, CASE_A, 2, "x"),
    ]
    found = case_agreements(answers)
    assert set(found) == {(MODEL, CASE_A), (OTHER, CASE_A)}
    summary = model_stability(answers)
    assert (summary[MODEL].stability, summary[MODEL].stable_cases, summary[MODEL].compared_cases) == (2 / 3, 0, 1)
    assert (summary[OTHER].stability, summary[OTHER].stable_cases) == (1.0, 1)


def test_one_run_per_case_has_no_stability_to_report() -> None:
    summary = model_stability([answer(MODEL, CASE_A, 1, "x"), answer(MODEL, CASE_B, 1, "y")])
    assert (summary[MODEL].stability, summary[MODEL].compared_cases) == (None, 0)
    assert model_stability([]) == {}


def test_replication_compares_the_same_case_model_and_run_and_counts_what_has_no_partner() -> None:
    earlier = [answer(MODEL, CASE_A, 1, "x"), answer(MODEL, CASE_A, 2, "y"), answer(MODEL, CASE_B, 1, "z")]
    current = [
        answer(MODEL, CASE_A, 1, " x"),
        answer(MODEL, CASE_A, 2, "different"),
        answer(MODEL, CASE_B, 1, "z"),
        answer(MODEL, CASE_B, 2, "z"),
        answer(OTHER, CASE_A, 1, "x"),
    ]
    found = replication(current, earlier)
    assert (found[MODEL].same, found[MODEL].compared, found[MODEL].skipped) == (2, 3, 1)
    assert (found[OTHER].same, found[OTHER].compared, found[OTHER].skipped) == (0, 0, 1)
