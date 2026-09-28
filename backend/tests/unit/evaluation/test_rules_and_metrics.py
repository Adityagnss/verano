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
