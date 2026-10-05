"""
Test cases from the rows of a table (`data.cases` in verano.yaml).

Verano stores a real test case as one input file, with its correct answer in a golden file that
names the input file. This turns each row into exactly that, so a plain `ticket,expected` table
works. The files are made the same way every time (numbered in row order, UTF-8, no timestamps),
so pushing unchanged data again produces byte-identical files and nothing new is uploaded.
"""

import csv
import hashlib
import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from verano.spec import Cases

MAX_CASES = 500
MAX_INPUT_CHARS = 100_000
SUFFIXES = {".csv", ".tsv", ".json", ".jsonl", ".ndjson"}
GOLDEN_COLUMNS = ["input_file", "expected_output", "category", "tags", "rubric"]
GOLDEN_MAPPING = {name: name for name in GOLDEN_COLUMNS}


@dataclass(frozen=True)
class Case:
    number: int
    filename: str
    text: str
    expected: str
    rubric: str
    category: str
    tags: str


@dataclass(frozen=True)
class Built:
    cases: list[Case]
    skipped: list[str]
    problems: list[str]


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, bool | int | float):
        return str(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def read_rows(path: Path) -> list[dict[str, str]]:
    """The rows of a table as text, whatever the format; raises ValueError with a plain reason."""
    suffix = path.suffix.lower()
    raw = path.read_text(encoding="utf-8-sig")
    if suffix in {".csv", ".tsv"}:
        reader = csv.DictReader(io.StringIO(raw), delimiter="\t" if suffix == ".tsv" else ",")
        if not reader.fieldnames:
            raise ValueError("the file has no header row")
        return [{k: _text(v) for k, v in row.items() if k is not None} for row in reader]
    if suffix in {".jsonl", ".ndjson"}:
        rows = []
        for number, line in enumerate(raw.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except ValueError as exc:
                raise ValueError(f"line {number} is not valid JSON") from exc
    else:
        try:
            rows = json.loads(raw)
        except ValueError as exc:
            raise ValueError("the file is not valid JSON") from exc
        if not isinstance(rows, list):
            raise ValueError("the JSON must be a list of objects")
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError("every row must be an object with named fields")
    return [{str(k): _text(v) for k, v in row.items()} for row in rows]


def build(rows: list[dict[str, str]], spec: Cases) -> Built:
    columns = set().union(*(row.keys() for row in rows)) if rows else set()
    wanted = {
        "input": spec.input,
        "expected": spec.expected,
        "rubric": spec.rubric,
        "category": spec.category,
        "tags": spec.tags,
    }
    problems = [
        f"the column '{name}' (for {role}) is not in the file; it has: {', '.join(sorted(columns)) or 'no columns'}"
        for role, name in wanted.items()
        if name is not None and name not in columns
    ]
    if problems:
        return Built([], [], problems)
    kept: list[tuple[int, dict[str, str]]] = []
    skipped: list[str] = []
    for number, row in enumerate(rows, start=1):
        text = row.get(spec.input, "").strip()
        answer = (row.get(spec.expected, "") if spec.expected else "").strip()
        criteria = (row.get(spec.rubric, "") if spec.rubric else "").strip()
        if not text:
            skipped.append(f"row {number}: the input is empty")
        elif not answer and not criteria:
            skipped.append(f"row {number}: no correct answer")
        elif len(text) > MAX_INPUT_CHARS:
            problems.append(f"row {number}: the input is longer than {MAX_INPUT_CHARS:,} characters")
        else:
            kept.append((number, row))
    if not kept and not problems:
        problems.append("no row has both an input and a correct answer")
    if len(kept) > MAX_CASES:
        problems.append(f"{len(kept)} usable rows; at most {MAX_CASES} per prompt (use a smaller file)")
    width = max(4, len(str(len(kept))))
    cases = [
        Case(
            number=number,
            filename=f"case-{index:0{width}d}.txt",
            text=row[spec.input].strip(),
            expected=(row.get(spec.expected, "") if spec.expected else "").strip(),
            rubric=(row.get(spec.rubric, "") if spec.rubric else "").strip(),
            category=(row.get(spec.category, "") if spec.category else "").strip(),
            tags=(row.get(spec.tags, "") if spec.tags else "").strip(),
        )
        for index, (number, row) in enumerate(kept, start=1)
    ]
    return Built(cases, skipped, problems)


def case_file(case: Case) -> bytes:
    return case.text.encode("utf-8")


def golden_file(cases: list[Case]) -> bytes:
    """The answers, one row per case, each naming the input file it belongs to."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(GOLDEN_COLUMNS)
    for case in cases:
        writer.writerow([case.filename, case.expected, case.category, case.tags, case.rubric])
    return out.getvalue().encode("utf-8")
