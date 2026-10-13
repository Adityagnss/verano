"""Unit tests for spotting a file of checks dropped where inputs go."""

from typing import Any

import pytest

from app.modules.datasets.domain import CHECKS_WARNING, checks_warning

pytestmark = pytest.mark.unit

CHECKS: list[dict[str, Any]] = [
    {"type": "must_not_contain", "value": "I cannot help"},
    {"type": "must_contain", "value": "refund policy"},
    {"type": "max_word_count", "value": 40},
    {"type": "must_refuse_injection", "value": True},
]


def test_a_file_of_check_names_is_flagged_and_real_inputs_are_not() -> None:
    assert checks_warning(["type", "value"], CHECKS) == [CHECKS_WARNING.format(example="must_not_contain")]
    categories = [{"type": "billing", "message": "charged twice"}, {"type": "shipping", "message": "where is it"}]
    assert checks_warning(["type", "message"], categories) == []  # a `type` column that holds categories
    assert checks_warning(["message"], [{"message": "must_contain"}, {"message": "must_not_contain"}]) == []
    assert checks_warning(["type"], [{"type": "must_contain"}]) == []  # one value is not enough to say
