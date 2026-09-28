"""
Pure dataset logic: suggesting and checking a column mapping, turning one source row into a
test case (or into the reasons it can't be one), and building the validation report.

- `suggest_mapping` matches prompt inputs by name, then answer / rubric / category / tags
  columns by synonym (config/column_synonyms.yaml). For a system-only prompt, whose one
  required input is the "User message input", a single remaining column is suggested for it.
- `mapping_problems` lists everything wrong with a mapping at once: unknown columns, a
  column used for two things, required inputs left unmapped.
- `evaluate_row` is the single definition of a valid row: every required input has a
  value, and a golden-set row has an expected output or a rubric.
- `clean_header` makes header cells usable as column names: blanks become `column_N`,
  repeats get a suffix, a stray byte-order mark is dropped.
- `ReportBuilder` counts issues with their row numbers (the file's own numbering: the
  spreadsheet row, the JSONL line, the JSON item), listing at most N rows per issue.
No I/O.
"""

import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from app.modules.datasets.schemas import (
    ColumnMapping,
    FileFormat,
    InputFileKind,
    IssueKind,
    ValidationIssue,
    ValidationReport,
)
from app.modules.prompts.schemas import USER_MESSAGE_INPUT

SEPARATORS = re.compile(r"[^0-9a-z]+")
LIST_SPLIT = re.compile(r"\s*[,;]\s*")
MISSING_VALUE = "No value for {field}"
MISSING_ANSWER = "No expected output or rubric"
DUPLICATE = "Exact duplicate of an earlier row"
UNKNOWN_COLUMN = "Column '{column}' isn't in this file."
COLUMN_TWICE = "Column '{column}' is mapped to more than one target."
INPUT_UNMAPPED = "The prompt input '{name}' needs a column."
UNKNOWN_INPUT = "'{name}' isn't an input of this prompt."


class ColumnSynonyms(BaseModel):
    expected_output: list[str]
    rubric: list[str]
    category: list[str]
    tags: list[str]


@dataclass(frozen=True)
class SourceRow:
    number: int
    values: dict[str, Any] | None
    error: str | None = None


@dataclass(frozen=True)
class ItemDraft:
    inputs: dict[str, Any]
    expected_output: str | None
    rubric: list[str] | None
    category: str
    tags: list[str]
    extra: dict[str, Any]
    source_row: int


@dataclass(frozen=True)
class RowIssue:
    kind: IssueKind
    target: str | None
    message: str


def normalize(name: str) -> str:
    return SEPARATORS.sub("_", name.strip().lower()).strip("_")


def _first_match(columns: list[str], candidates: Iterable[str], taken: set[str]) -> str | None:
    by_name = {normalize(column): column for column in columns if column not in taken}
    return next((by_name[normalize(c)] for c in candidates if normalize(c) in by_name), None)


def suggest_mapping(columns: list[str], required_inputs: list[str], synonyms: ColumnSynonyms) -> ColumnMapping:
    taken: set[str] = set()
    inputs: dict[str, str] = {}
    for name in required_inputs:
        column = _first_match(columns, [name], taken)
        if column is not None:
            inputs[name] = column
            taken.add(column)
    targets: dict[str, str | None] = {}
    for target in ("expected_output", "rubric", "category", "tags"):
        targets[target] = _first_match(columns, getattr(synonyms, target), taken)
        taken.update(column for column in [targets[target]] if column)
    remaining = [column for column in columns if column not in taken]
    if USER_MESSAGE_INPUT in required_inputs and USER_MESSAGE_INPUT not in inputs and len(remaining) == 1:
        inputs[USER_MESSAGE_INPUT] = remaining[0]
    return ColumnMapping(inputs=inputs, **targets)


def mapping_problems(mapping: ColumnMapping, columns: list[str], required_inputs: list[str]) -> list[str]:
    known = set(columns)
    assigned = mapping.assigned()
    used = [column for _, column in assigned] + mapping.ignored
    problems = [UNKNOWN_COLUMN.format(column=column) for column in dict.fromkeys(used) if column not in known]
    problems += [COLUMN_TWICE.format(column=column) for column in dict.fromkeys(used) if used.count(column) > 1]
    problems += [UNKNOWN_INPUT.format(name=name) for name in mapping.inputs if name not in required_inputs]
    problems += [INPUT_UNMAPPED.format(name=name) for name in required_inputs if name not in mapping.inputs]
    return problems


def kind_of(mapping: ColumnMapping) -> InputFileKind:
    return InputFileKind.GOLDEN_SET if mapping.has_answers else InputFileKind.RAW_INPUTS


def is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def as_text(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)


def as_list(value: Any, splitter: re.Pattern[str]) -> list[str]:
    if is_blank(value):
        return []
    if isinstance(value, list):
        return [as_text(item).strip() for item in value if not is_blank(item)]
    return [part for part in splitter.split(as_text(value).strip()) if part]


RUBRIC_SPLIT = re.compile(r"\s*(?:\r?\n)+\s*")


def evaluate_row(
    row: SourceRow, mapping: ColumnMapping, required_inputs: list[str], default_category: str
) -> ItemDraft | list[RowIssue]:
    if row.values is None:
        return [RowIssue(IssueKind.INVALID_ROW, None, row.error or "This row can't be read")]
    values = row.values
    issues = [
        RowIssue(IssueKind.MISSING_VALUE, name, MISSING_VALUE.format(field=name))
        for name in required_inputs
        if is_blank(values.get(mapping.inputs.get(name, "")))
    ]
    expected = values.get(mapping.expected_output) if mapping.expected_output else None
    rubric = as_list(values.get(mapping.rubric), RUBRIC_SPLIT) if mapping.rubric else []
    if mapping.has_answers and is_blank(expected) and not rubric:
        issues.append(RowIssue(IssueKind.MISSING_ANSWER, None, MISSING_ANSWER))
    if issues:
        return issues
    used = {column for _, column in mapping.assigned()} | set(mapping.ignored)
    category = values.get(mapping.category) if mapping.category else None
    return ItemDraft(
        inputs={name: values[column] for name, column in mapping.inputs.items()},
        expected_output=None if is_blank(expected) else as_text(expected).strip(),
        rubric=rubric or None,
        category=default_category if is_blank(category) else as_text(category).strip(),
        tags=as_list(values.get(mapping.tags), LIST_SPLIT) if mapping.tags else [],
        extra={column: value for column, value in values.items() if column not in used},
        source_row=row.number,
    )


def clean_header(cells: list[Any]) -> list[str]:
    names: list[str] = []
    for index, cell in enumerate(cells, start=1):
        base = f"column_{index}" if is_blank(cell) else as_text(cell).strip().lstrip("\ufeff")
        name, suffix = base, 2
        while name in names:
            name, suffix = f"{base}_{suffix}", suffix + 1
        names.append(name)
    return names


def duplicate_key(item: ItemDraft) -> bytes:
    payload = json.dumps([item.inputs, item.expected_output, item.rubric], sort_keys=True, default=str)
    return hashlib.blake2b(payload.encode(), digest_size=16).digest()


@dataclass
class _IssueTally:
    kind: IssueKind
    target: str | None
    message: str
    count: int = 0
    rows: list[int] = field(default_factory=list)


@dataclass
class ReportBuilder:
    max_listed: int
    total_rows: int = 0
    valid_rows: int = 0
    skipped_rows: int = 0
    duplicates: int = 0
    _issues: dict[tuple[IssueKind, str | None], _IssueTally] = field(default_factory=dict)

    def _note(self, kind: IssueKind, target: str | None, message: str, row: int) -> None:
        tally = self._issues.setdefault((kind, target), _IssueTally(kind, target, message))
        tally.count += 1
        if len(tally.rows) < self.max_listed:
            tally.rows.append(row)

    def reject(self, row: int, issues: list[RowIssue]) -> None:
        self.total_rows += 1
        self.skipped_rows += 1
        for issue in issues:
            self._note(issue.kind, issue.target, issue.message, row)

    def duplicate(self, row: int) -> None:
        self.total_rows += 1
        self.duplicates += 1
        self._note(IssueKind.DUPLICATE, None, DUPLICATE, row)

    def accept(self) -> None:
        self.total_rows += 1
        self.valid_rows += 1

    def build(
        self, kind: InputFileKind, file_format: FileFormat, encoding: str | None, sheet: str | None, warnings: list[str]
    ) -> ValidationReport:
        return ValidationReport(
            kind=kind,
            format=file_format,
            encoding=encoding,
            sheet=sheet,
            total_rows=self.total_rows,
            valid_rows=self.valid_rows,
            skipped_rows=self.skipped_rows,
            duplicates_removed=self.duplicates,
            issues=[
                ValidationIssue(kind=t.kind, field=t.target, message=t.message, count=t.count, rows=t.rows)
                for t in self._issues.values()
            ],
            warnings=warnings,
        )
