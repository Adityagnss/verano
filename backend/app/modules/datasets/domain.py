"""
Pure dataset logic for golden sets: suggesting and checking a column mapping, turning one
golden-set row into an expected output (or into the reasons it can't be one), pairing
those entries with input files, and building the validation report.

- `suggest_mapping` matches answer / rubric / category / tags / input-file-name columns by
  synonym (config/column_synonyms.yaml). Nothing is required: a row with no expected-output
  column is itself the expected output (a JSON answer), minus any mapped columns.
- `mapping_problems` lists everything wrong with a mapping at once: unknown columns and a
  column used for two things.
- `evaluate_row` is the single definition of a valid entry: it has an expected output or a
  rubric.
- `Pairing` pairs entries with input files: by file name where the entry names one, the
  rest in order.
- `clean_header` makes header cells usable as column names: blanks become `column_N`,
  repeats get a suffix, a stray byte-order mark is dropped.
- `ReportBuilder` counts issues with their row numbers (the file's own numbering: the
  spreadsheet row, the JSONL line, the JSON item), listing at most N rows per issue.
- `TableSummary` is what a model sees of a table file (see `processing.attach`).
No I/O.
"""

import json
import math
import random
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel

from app.modules.datasets.schemas import (
    ColumnMapping,
    FileFormat,
    InputFileKind,
    IssueKind,
    ItemSource,
    Split,
    ValidationIssue,
    ValidationReport,
)

SEPARATORS = re.compile(r"[^0-9a-z]+")
LIST_SPLIT = re.compile(r"\s*[,;]\s*")
MISSING_ANSWER = "No expected output or rubric"
UNPAIRED = "No input file to pair this entry with. Upload the input files first."
UNKNOWN_COLUMN = "Column '{column}' isn't in this file."
COLUMN_TWICE = "Column '{column}' is mapped to more than one target."


class ColumnSynonyms(BaseModel):
    expected_output: list[str]
    rubric: list[str]
    category: list[str]
    tags: list[str]
    input_file: list[str]


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
    input_file: str | None = None


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


def suggest_mapping(columns: list[str], synonyms: ColumnSynonyms) -> ColumnMapping:
    taken: set[str] = set()
    targets: dict[str, str | None] = {}
    for target in ("expected_output", "rubric", "category", "tags", "input_file"):
        targets[target] = _first_match(columns, getattr(synonyms, target), taken)
        taken.update(column for column in [targets[target]] if column)
    return ColumnMapping(**targets)


def mapping_problems(mapping: ColumnMapping, columns: list[str]) -> list[str]:
    known = set(columns)
    used = [column for _, column in mapping.assigned()] + mapping.ignored
    problems = [UNKNOWN_COLUMN.format(column=column) for column in dict.fromkeys(used) if column not in known]
    problems += [COLUMN_TWICE.format(column=column) for column in dict.fromkeys(used) if used.count(column) > 1]
    return problems


MESSAGE_COLUMNS = {
    "message", "user_message", "customer_message", "text", "input", "question", "prompt", "query", "content",
    "utterance", "ticket", "body",
}  # fmt: skip


def message_column(columns: list[str]) -> str | None:
    """The column that holds what the prompt receives: a column named like a message, else the only column."""
    named = next((column for column in columns if normalize(column) in MESSAGE_COLUMNS), None)
    return named or (columns[0] if len(columns) == 1 else None)


def row_input(columns: list[str], values: dict[str, Any]) -> str | None:
    """What one row sends to the prompt: its message column's text, else every filled column as `name: value`
    lines. None for a row with nothing in it."""
    column = message_column(columns)
    if column is not None:
        value = values.get(column)
        return None if is_blank(value) else as_text(value).strip()
    lines = [f"{name}: {as_text(value).strip()}" for name, value in values.items() if not is_blank(value)]
    return "\n".join(lines) or None


def is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def as_text(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def as_list(value: Any, splitter: re.Pattern[str]) -> list[str]:
    if is_blank(value):
        return []
    if isinstance(value, list):
        return [as_text(item).strip() for item in value if not is_blank(item)]
    return [part for part in splitter.split(as_text(value).strip()) if part]


RUBRIC_SPLIT = re.compile(r"\s*(?:\r?\n)+\s*")


def evaluate_row(row: SourceRow, mapping: ColumnMapping, default_category: str) -> ItemDraft | list[RowIssue]:
    if row.values is None:
        return [RowIssue(IssueKind.INVALID_ROW, None, row.error or "This row can't be read")]
    values = row.values
    used = {column for _, column in mapping.assigned()} | set(mapping.ignored)
    rubric = as_list(values.get(mapping.rubric), RUBRIC_SPLIT) if mapping.rubric else []
    if mapping.expected_output:
        expected = values.get(mapping.expected_output)
    elif rubric:
        expected = None
    else:
        rest = {column: value for column, value in values.items() if column not in used and not is_blank(value)}
        expected = json.dumps(rest, ensure_ascii=False, default=str) if rest else None
    if is_blank(expected) and not rubric:
        return [RowIssue(IssueKind.MISSING_ANSWER, None, MISSING_ANSWER)]
    category = values.get(mapping.category) if mapping.category else None
    name = values.get(mapping.input_file) if mapping.input_file else None
    return ItemDraft(
        inputs={},
        expected_output=None if is_blank(expected) else as_text(expected).strip(),
        rubric=rubric or None,
        category=default_category if is_blank(category) else as_text(category).strip(),
        tags=as_list(values.get(mapping.tags), LIST_SPLIT) if mapping.tags else [],
        extra={},
        source_row=row.number,
        input_file=None if is_blank(name) else as_text(name).strip(),
    )


class Pairing:
    """Pairs golden entries with input files as the entries stream past, holding at most one
    entry per input file: an entry naming a file takes it, the others take the files left,
    in order, once all entries are seen."""

    def __init__(self, filenames: list[str]) -> None:
        self._filenames = filenames
        self._taken: set[int] = set()
        self._pending: list[ItemDraft] = []
        self._pairs: list[tuple[ItemDraft, int]] = []
        self._unpaired: list[int] = []

    def add(self, entry: ItemDraft) -> None:
        if entry.input_file is not None:
            at = next(
                (i for i, name in enumerate(self._filenames) if name == entry.input_file and i not in self._taken), None
            )
            if at is None:
                self._unpaired.append(entry.source_row)
            else:
                self._taken.add(at)
                self._pairs.append((entry, at))
        elif len(self._pending) < len(self._filenames):
            self._pending.append(entry)
        else:
            self._unpaired.append(entry.source_row)

    def finish(self) -> tuple[list[tuple[ItemDraft, int]], list[int]]:
        free = [i for i in range(len(self._filenames)) if i not in self._taken]
        for entry, at in zip(self._pending, free, strict=False):
            self._pairs.append((entry, at))
        self._unpaired += [entry.source_row for entry in self._pending[len(free) :]]
        return self._pairs, sorted(self._unpaired)


def clean_header(cells: list[Any]) -> list[str]:
    names: list[str] = []
    for index, cell in enumerate(cells, start=1):
        base = f"column_{index}" if is_blank(cell) else as_text(cell).strip().lstrip("\ufeff")
        name, suffix = base, 2
        while name in names:
            name, suffix = f"{base}_{suffix}", suffix + 1
        names.append(name)
    return names


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

    def unpaired(self, row: int) -> None:
        self.valid_rows -= 1
        self.skipped_rows += 1
        self._note(IssueKind.UNPAIRED, None, UNPAIRED, row)

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
            issues=[
                ValidationIssue(kind=t.kind, field=t.target, message=t.message, count=t.count, rows=t.rows)
                for t in self._issues.values()
            ],
            warnings=warnings,
        )


@dataclass(frozen=True)
class SplitCandidate:
    id: Any
    category: str
    source: ItemSource


def assign_splits(items: list[SplitCandidate], holdout_ratio: float, seed: int) -> dict[Any, Split]:
    """
    Stratified optimize / holdout split (DEVELOPMENT.md 2.4). Each (category, source)
    stratum gets its share of the holdout; the rounding remainders go to the strata with
    the largest fractional parts, so the overall holdout is round(N x ratio). If golden rows
    exist, at least one lands in the holdout. Deterministic for a given seed.
    """
    strata: dict[tuple[str, ItemSource], list[SplitCandidate]] = {}
    for item in sorted(items, key=lambda i: str(i.id)):
        strata.setdefault((item.category, item.source), []).append(item)
    rng = random.Random(seed)
    for members in strata.values():
        rng.shuffle(members)
    exact = {key: len(members) * holdout_ratio for key, members in strata.items()}
    counts = {key: math.floor(value) for key, value in exact.items()}
    remainder = round(len(items) * holdout_ratio) - sum(counts.values())
    for key in sorted(exact, key=lambda k: (counts[k] - exact[k], k[0], k[1]))[:remainder]:
        counts[key] += 1
    golden = [key for key in strata if key[1] is ItemSource.GOLDEN]
    if golden and not any(counts[key] for key in golden):
        counts[max(golden, key=lambda k: len(strata[k]))] += 1
    return {
        item.id: Split.HOLDOUT if index < counts[key] else Split.OPTIMIZE
        for key, members in strata.items()
        for index, item in enumerate(members)
    }


class TableSummary:
    """What a model needs to see of a table file, built in one streaming pass: for every
    column its type and statistics over the whole file, then the first rows as samples."""

    def __init__(self, filename: str, columns: list[str], sample_rows: int, max_distinct: int, examples: int) -> None:
        self._filename = filename
        self._columns = dict.fromkeys(columns)
        self._distinct: dict[str, set[str]] = {column: set() for column in columns}
        self._types: dict[str, set[str]] = {column: set() for column in columns}
        self._capped: set[str] = set()
        self._samples: list[dict[str, Any]] = []
        self._sample_rows = sample_rows
        self._max_distinct = max_distinct
        self._examples = examples
        self.count = 0

    def add(self, values: dict[str, Any]) -> None:
        self.count += 1
        if len(self._samples) < self._sample_rows:
            self._samples.append(values)
        for column, value in values.items():
            if column not in self._distinct:
                self._columns[column] = None
                self._distinct[column], self._types[column] = set(), set()
            if is_blank(value):
                continue
            self._types[column].add(_type_name(value))
            seen = self._distinct[column]
            if len(seen) < self._max_distinct:
                seen.add(as_text(value))
            else:
                self._capped.add(column)

    def render(self) -> str:
        lines = [f"FILE: {self._filename}", f"ROWS: {self.count}", "", "===== COLUMN TYPES ====="]
        for column in self._columns:
            seen = self._distinct[column]
            info: dict[str, Any] = {
                "column": column,
                "type": _column_type(self._types[column]),
                "distinct_count": len(seen),
                "all_null": not seen,
            }
            if column in self._capped:
                info["distinct_count_note"] = f"at least {self._max_distinct}"
            if 0 < len(seen) <= self._examples:
                info["example_values"] = sorted(seen)
            lines.append(json.dumps(info, ensure_ascii=False))
        rows = [[row.get(column) for column in self._columns] for row in self._samples]
        lines += ["", "===== SAMPLE ROWS =====", "Values are positionally aligned to these columns:"]
        lines.append(json.dumps(list(self._columns), ensure_ascii=False))
        lines += [json.dumps(row, ensure_ascii=False, default=str) for row in rows]
        return "\n".join(lines)


def _type_name(value: Any) -> str:
    if isinstance(value, bool):
        return "BOOLEAN"
    if isinstance(value, int):
        return "BIGINT"
    if isinstance(value, float):
        return "DOUBLE"
    if isinstance(value, (datetime, date)):
        return "DATE"
    return "VARCHAR"


def _column_type(types: set[str]) -> str:
    if not types:
        return "EMPTY"
    if types == {"BIGINT", "DOUBLE"}:
        return "DOUBLE"
    return next(iter(types)) if len(types) == 1 else "VARCHAR"
