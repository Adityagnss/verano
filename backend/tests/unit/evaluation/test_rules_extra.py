"""The extra rule checks (27 in all with the originals): each passes a known-good answer and fails a known-bad one."""

from typing import Any

import pytest

from app.modules.evaluation.domain import EvalCase
from app.modules.evaluation.plugins.rules import RULES
from app.modules.evaluation.plugins.rules_extra import RULE_INFO
from app.modules.generator.schemas import TaskSpec

SPEC = TaskSpec(
    task_type="generation", goal="Reply to a customer", input_variables=["ticket"], output_format="free_text"
)
SEARCH = {"name": "search", "arguments": {"query": "shoes"}}
BUY = {"name": "buy", "arguments": {"item": "42"}}
DELETE = {"name": "delete", "arguments": {}}


def case(output: str, expected: str | None = None, calls: list[dict[str, Any]] | None = None) -> EvalCase:
    return EvalCase(
        inputs={"ticket": "hello"},
        output=output,
        expected=expected,
        rubric=None,
        task_spec=SPEC,
        tool_calls=calls or [],
    )


# rule, config, threshold, (good output, expected, calls), (bad output, expected, calls)
CASES: list[tuple[str, dict[str, Any], float, tuple[Any, ...], tuple[Any, ...]]] = [
    (
        "contains_all",
        {"values": ["refund", "days"]},
        1.0,
        ("a refund in 5 days", None, None),
        ("nothing here", None, None),
    ),
    ("contains_any", {"values": ["sorry", "apolog"]}, 1.0, ("We apologize", None, None), ("Hello", None, None)),
    ("not_contains", {"values": ["password"]}, 1.0, ("all good", None, None), ("your password is x", None, None)),
    ("regex_match", {"pattern": r"\d{3}-\d{4}"}, 1.0, ("call 555-1234", None, None), ("call me", None, None)),
    ("regex_absent", {"pattern": r"\bTODO\b"}, 1.0, ("done", None, None), ("TODO fix", None, None)),
    ("starts_with", {"value": "Dear"}, 1.0, ("Dear Sam", None, None), ("Hi Sam", None, None)),
    ("ends_with", {"value": "Regards"}, 1.0, ("Thanks. Regards", None, None), ("Thanks", None, None)),
    ("char_length", {"min": 5, "max": 10}, 1.0, ("hello!!", None, None), ("hi", None, None)),
    ("word_count", {"min": 2, "max": 3}, 1.0, ("two words", None, None), ("one", None, None)),
    ("numeric_close", {"tolerance": 0.5}, 1.0, ("about 10.2", "10", None), ("42", "10", None)),
    ("no_pii", {}, 1.0, ("Thanks for writing", None, None), ("mail me at ada@example.com", None, None)),
    ("valid_url", {}, 1.0, ("https://example.com/a", None, None), ("not a url", None, None)),
    ("valid_xml", {}, 1.0, ("<a><b/></a>", None, None), ("<a>", None, None)),
    ("valid_yaml", {}, 1.0, ("a: 1", None, None), ("a: [1", None, None)),
    ("token_overlap_f1", {}, 0.8, ("the cat sat", "the cat sat", None), ("dogs run fast", "the cat sat", None)),
    ("edit_similarity", {}, 0.8, ("hello world", "hello world", None), ("zzzz", "hello world", None)),
    (
        "bleu",
        {},
        0.8,
        ("the cat sat on the mat", "the cat sat on the mat", None),
        ("dogs run fast now", "the cat sat on the mat", None),
    ),
    (
        "rouge_l",
        {},
        0.8,
        ("the cat sat on the mat", "the cat sat on the mat", None),
        ("dogs run fast now", "the cat sat on the mat", None),
    ),
    (
        "tool_called",
        {"name": "search", "arguments": {"query": "shoes"}},
        1.0,
        ("ok", None, [SEARCH]),
        ("ok", None, [DELETE]),
    ),
    ("tool_not_called", {"names": ["delete"]}, 1.0, ("ok", None, [SEARCH]), ("ok", None, [SEARCH, DELETE])),
    ("tool_order", {"names": ["search", "buy"]}, 1.0, ("ok", None, [SEARCH, BUY]), ("ok", None, [BUY, SEARCH])),
    ("max_tool_calls", {"limit": 1}, 1.0, ("ok", None, [SEARCH]), ("ok", None, [SEARCH, BUY])),
]


@pytest.mark.parametrize(("name", "config", "threshold", "good", "bad"), CASES, ids=[c[0] for c in CASES])
def test_a_rule_passes_a_good_answer_and_fails_a_bad_one(
    name: str, config: dict[str, Any], threshold: float, good: tuple[Any, ...], bad: tuple[Any, ...]
) -> None:
    rule = RULES[name]
    passed, failed = rule(case(*good), config, threshold), rule(case(*bad), config, threshold)
    assert passed is not None, name
    assert passed.passed, passed
    assert failed is not None, name
    assert not failed.passed, failed


def test_there_are_more_than_twenty_rules_and_each_is_described() -> None:
    assert len(RULES) >= 20
    assert set(RULE_INFO) == set(RULES)


def test_a_rule_without_what_it_needs_does_not_apply() -> None:
    assert RULES["contains_all"](case("x"), {}, 1.0) is None
    assert RULES["bleu"](case("x"), {}, 1.0) is None  # no expected answer
    assert RULES["regex_match"](case("x"), {"pattern": "("}, 1.0) is None  # a pattern that does not compile


def test_xml_with_an_entity_declaration_is_refused() -> None:
    bomb = '<!DOCTYPE a [<!ENTITY x "y">]><a>&x;</a>'
    result = RULES["valid_xml"](case(bomb), {}, 1.0)
    assert result is not None
    assert not result.passed


def test_pii_is_named_by_kind_but_never_printed() -> None:
    result = RULES["no_pii"](case("write to ada@example.com"), {}, 1.0)
    assert result is not None
    assert "email" in result.reason
    assert "ada@example.com" not in result.reason
