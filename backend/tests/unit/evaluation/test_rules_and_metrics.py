"""Unit tests for the rule evaluators and the per-model metrics."""

import uuid
from decimal import Decimal

import pytest

from app.modules.evaluation.domain import EvalCase
from app.modules.evaluation.metrics import CaseOutcome, model_metrics
from app.modules.evaluation.plugins.rules import RULES
from app.modules.generator.schemas import TaskSpec

pytestmark = pytest.mark.unit

SPEC = TaskSpec(
    task_type="classification",
    goal="Classify tickets",
    input_variables=["ticket"],
    output_format="single_label",
    allowed_outputs=["billing", "shipping"],
    constraints=["one word", "lowercase", "a friendly tone"],
)


def case(output: str, expected: str | None = "billing") -> EvalCase:
    return EvalCase(inputs={"ticket": "charged twice"}, output=output, expected=expected, rubric=None, task_spec=SPEC)


def test_rules_normalize_and_skip_what_does_not_apply() -> None:
    def passed(name: str, output: str) -> bool | None:
        result = RULES[name](case(output), {}, 1.0)
        return None if result is None else result.passed

    assert passed("exact_match", " Billing. ") is True
    assert RULES["exact_match"](case("x", expected=None), {}, 1.0) is None
    assert passed("allowed_values", "refund") is False
    assert passed("json_valid", '```json\n{"a": 1}\n```') is True
    result = RULES["constraints"](case("Billing please"), {}, 1.0)
    assert result is not None
    assert result.value == 0.0
    assert "Not checked automatically: a friendly tone" in result.reason


def test_metrics_per_model() -> None:
    model, items = uuid.uuid4(), [uuid.uuid4(), uuid.uuid4()]

    def outcome(item: uuid.UUID, run: int, passed: bool) -> CaseOutcome:
        return CaseOutcome(model, "m", item, run, False, passed, 1.0 if passed else 0.0, 100, Decimal("0.01"))

    rows = [
        outcome(items[0], 1, True),
        outcome(items[0], 2, True),
        outcome(items[1], 1, True),
        outcome(items[1], 2, False),
    ]
    [metrics] = model_metrics(rows)
    assert (metrics.pass_rate, metrics.quality, metrics.consistency) == (0.75, 0.75, 0.5)
    assert metrics.cost == Decimal("0.04")
    assert metrics.cost_per_call == Decimal("0.01")


def test_a_case_with_an_unscored_check_is_not_judged_and_never_a_pass_or_a_zero() -> None:
    from app.modules.evaluation.domain import Score
    from app.modules.evaluation.metrics import WeightedScore, case_result

    good = WeightedScore(Score(1.0, True, "ok"), 1.0)
    missing = WeightedScore(Score(0.0, False, "the judge failed"), 1.0, scored=False)
    assert case_result([good]) == (True, 1.0, True)
    assert case_result([good, missing]) == (False, 0.0, False)
    assert case_result([missing]) == (False, 0.0, False)
    assert case_result([]) == (True, 1.0, True)


def test_unscored_cases_are_counted_and_left_out_of_quality_pass_rate_and_consistency() -> None:
    model, items = uuid.uuid4(), [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]

    def outcome(item: uuid.UUID, run: int, passed: bool, judged: bool = True) -> CaseOutcome:
        return CaseOutcome(model, "m", item, run, False, passed, 1.0 if passed else 0.0, 100, Decimal("0.01"), judged)

    rows = [
        outcome(items[0], 1, True),
        outcome(items[0], 2, True),
        outcome(items[1], 1, False, judged=False),
        outcome(items[1], 2, False, judged=False),
        outcome(items[2], 1, False),
        outcome(items[2], 2, True, judged=False),
    ]
    [metrics] = model_metrics(rows)
    assert (metrics.cases, metrics.judged_cases, metrics.unscored_cases) == (6, 3, 3)
    assert metrics.quality == pytest.approx(2 / 3)
    assert metrics.pass_rate == pytest.approx(2 / 3)
    assert metrics.consistency == 1.0
    assert metrics.cost == Decimal("0.06")
    assert metrics.cost_per_call == Decimal("0.01")


def test_a_model_with_nothing_judged_has_no_quality_instead_of_a_made_up_one() -> None:
    model, item = uuid.uuid4(), uuid.uuid4()
    rows = [CaseOutcome(model, "m", item, run, False, False, 0.0, 100, None, False) for run in (1, 2)]
    [metrics] = model_metrics(rows)
    assert (metrics.quality, metrics.pass_rate, metrics.consistency) == (None, None, None)
    assert (metrics.judged_cases, metrics.unscored_cases) == (0, 2)
