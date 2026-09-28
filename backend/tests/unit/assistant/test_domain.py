"""Unit tests for Improve's pure rules: failure tags, the best candidate and the honest verdict."""

import pytest

from app.modules.assistant.domain import best, prompt_diff, rule_tag, verdict

pytestmark = pytest.mark.unit


def test_rule_tags_best_candidate_and_verdict() -> None:
    assert rule_tag(None, {"call_error"}) == "call_error"
    assert rule_tag("  ", {"exact_match"}) == "empty"
    assert rule_tag("I'm sorry, I can't help", {"exact_match"}) == "refusal"
    assert rule_tag("Billing!", {"allowed_values", "exact_match"}) == "format_broken"
    assert rule_tag("shipping", {"exact_match"}) == "wrong_label"
    assert best({"a": 0.4, "b": 0.7, "c": None}) == "b"
    assert verdict(0.8, 0.6)[0] is True
    better, message = verdict(0.6, 0.6)
    assert better is False
    assert "No candidate beat" in message
    assert "+[system]" not in prompt_diff(("Be brief.", None), ("Be brief.", None))
    assert "+Reply with one word." in prompt_diff(("Be brief.", None), ("Be brief.\nReply with one word.", None))
