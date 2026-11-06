"""Mapping the columns of a table to prompt variables: what is wrong is listed at once, and an empty cell leaves
the row out.
"""

from app.modules.datasets.domain import row_inputs, variable_problems

COLUMNS = ["Question", "Context", "Language", "Answer"]


def test_a_good_mapping_has_no_problems() -> None:
    assert variable_problems({"question": "Question", "context": "Context"}, "Answer", None, COLUMNS) == []


def test_every_problem_is_listed_together() -> None:
    problems = variable_problems({"1st": "Question", "ctx": "Missing"}, "Nope", None, COLUMNS)
    assert len(problems) == 3
    assert any("'1st'" in p for p in problems)
    assert any("'Missing'" in p for p in problems)
    assert any("'Nope'" in p for p in problems)


def test_a_row_carries_every_variable_or_is_left_out_naming_the_empty_ones() -> None:
    variables = {"question": "Question", "context": "Context", "language": "Language"}
    found, empty = row_inputs(variables, {"Question": " Why? ", "Context": "docs", "Language": "en"})
    assert found == {"question": "Why?", "context": "docs", "language": "en"}
    assert empty == []
    found, empty = row_inputs(variables, {"Question": "Why?", "Context": "", "Language": None})
    assert empty == ["context", "language"]
    assert found == {"question": "Why?"}
