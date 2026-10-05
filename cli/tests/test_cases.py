"""Turning table rows into Verano test cases: reading, skipping, naming, and the golden file."""

import csv
import io
from pathlib import Path

import pytest

from verano.cases import MAX_CASES, build, case_file, golden_file, read_rows, sha256
from verano.spec import Cases


def spec(**extra: str | None) -> Cases:
    return Cases(file="x.csv", input="ticket", expected="expected", **extra)


def rows(*pairs: tuple[str, str]) -> list[dict[str, str]]:
    return [{"ticket": t, "expected": e} for t, e in pairs]


def test_csv_with_a_bom_quotes_newlines_and_unicode_is_read_as_text(tmp_path: Path) -> None:
    path = tmp_path / "t.csv"
    path.write_bytes('﻿ticket,expected\n"Two\nlines, with comma",billing\nZoë ünï,other\n'.encode())
    assert read_rows(path) == [
        {"ticket": "Two\nlines, with comma", "expected": "billing"},
        {"ticket": "Zoë ünï", "expected": "other"},
    ]


def test_tsv_jsonl_and_json_are_read_too_and_values_become_text(tmp_path: Path) -> None:
    (tmp_path / "t.tsv").write_text("ticket\texpected\nhello there\tgreeting\n")
    assert read_rows(tmp_path / "t.tsv") == [{"ticket": "hello there", "expected": "greeting"}]
    (tmp_path / "t.jsonl").write_text('{"ticket": "a", "expected": 5}\n\n{"ticket": "b", "expected": null}\n')
    assert read_rows(tmp_path / "t.jsonl") == [{"ticket": "a", "expected": "5"}, {"ticket": "b", "expected": ""}]
    (tmp_path / "t.json").write_text('[{"ticket": "a", "expected": {"k": [1, 2]}}]')
    assert read_rows(tmp_path / "t.json") == [{"ticket": "a", "expected": '{"k": [1, 2]}'}]


@pytest.mark.parametrize(
    ("name", "content", "reason"),
    [
        ("a.csv", "", "no header row"),
        ("a.jsonl", '{"a": 1}\nnot json\n', "line 2 is not valid JSON"),
        ("a.json", "{oops", "not valid JSON"),
        ("a.json", '{"a": 1}', "must be a list of objects"),
        ("a.json", "[1, 2]", "every row must be an object"),
    ],
)
def test_a_file_that_is_not_a_table_says_why(tmp_path: Path, name: str, content: str, reason: str) -> None:
    (tmp_path / name).write_text(content)
    with pytest.raises(ValueError, match=reason):
        read_rows(tmp_path / name)


def test_rows_without_an_input_or_an_answer_are_skipped_and_named() -> None:
    built = build(rows(("good", "a"), ("  ", "b"), ("no answer", " "), ("fine", "c")), spec())
    assert [c.text for c in built.cases] == ["good", "fine"]
    assert built.skipped == ["row 2: the input is empty", "row 3: no correct answer"]
    assert built.problems == []


def test_a_rubric_can_stand_in_for_an_exact_answer() -> None:
    built = build([{"ticket": "t", "criteria": "polite\nshort"}], Cases(file="x", input="ticket", rubric="criteria"))
    assert built.problems == []
    assert built.cases[0].rubric == "polite\nshort"
    assert built.cases[0].expected == ""


def test_a_missing_column_is_named_with_the_ones_that_exist() -> None:
    built = build(rows(("a", "b")), spec(category="kind", tags="labels"))
    assert built.cases == []
    assert any(
        "the column 'kind' (for category) is not in the file; it has: expected, ticket" in p for p in built.problems
    )
    assert any("'labels' (for tags)" in p for p in built.problems)


def test_nothing_usable_too_many_and_too_long_are_problems() -> None:
    assert "no row has both an input and a correct answer" in build(rows(("a", "")), spec()).problems
    empty = build([], spec()).problems
    assert "the column 'ticket' (for input) is not in the file; it has: no columns" in empty
    assert len(empty) == 2
    many = build(rows(*[(f"t{i}", "x") for i in range(MAX_CASES + 1)]), spec())
    assert any(f"{MAX_CASES + 1} usable rows; at most {MAX_CASES}" in p for p in many.problems)
    long = build(rows(("x" * 100_001, "a")), spec())
    assert any("row 1: the input is longer than 100,000" in p for p in long.problems)


def test_files_are_named_in_row_order_and_made_the_same_way_every_time() -> None:
    table = rows(("one", "a"), ("", "skipped"), ("two", "b"))
    first, second = build(table, spec()), build(table, spec())
    assert [c.filename for c in first.cases] == ["case-0001.txt", "case-0002.txt"]
    assert [sha256(case_file(c)) for c in first.cases] == [sha256(case_file(c)) for c in second.cases]
    assert golden_file(first.cases) == golden_file(second.cases)
    assert case_file(first.cases[0]) == b"one"


def test_names_get_wider_for_big_tables_and_stay_sorted() -> None:
    built = build(rows(*[(f"t{i}", "x") for i in range(12000 // 40)]), spec())
    assert built.cases[0].filename == "case-0001.txt"
    assert built.cases[-1].filename == "case-0300.txt"


def test_the_golden_file_names_each_input_file_and_survives_commas_quotes_and_newlines() -> None:
    built = build(
        [
            {"ticket": "a", "expected": 'say "hi", please', "kind": "edge", "labels": "x; y"},
            {"ticket": "b", "expected": "two\nlines", "kind": "", "labels": ""},
        ],
        spec(category="kind", tags="labels"),
    )
    parsed = list(csv.DictReader(io.StringIO(golden_file(built.cases).decode())))
    assert parsed[0] == {
        "input_file": "case-0001.txt",
        "expected_output": 'say "hi", please',
        "category": "edge",
        "tags": "x; y",
        "rubric": "",
    }
    assert parsed[1]["expected_output"] == "two\nlines"
    assert parsed[1]["input_file"] == "case-0002.txt"
