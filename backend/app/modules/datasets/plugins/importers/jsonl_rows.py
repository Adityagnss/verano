"""
JSON Lines reader: one object per line, read line by line. Rows are numbered by line; a
line that isn't valid JSON, or isn't an object, is reported as an invalid row instead of
failing the whole file. Blank lines are skipped.
"""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import ClassVar, TextIO

from app.modules.datasets.domain import SourceRow
from app.modules.datasets.plugins.importers.base import ROW_READERS, ReadLimits, ReadOptions, RowStream, is_blank_row
from app.modules.datasets.schemas import FileFormat

NOT_JSON = "This line isn't valid JSON"
NOT_AN_OBJECT = "This line isn't an object with named fields"


def _lines(handle: TextIO) -> Iterator[SourceRow]:
    for number, line in enumerate(handle, start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            yield SourceRow(number, None, NOT_JSON)
            continue
        if not isinstance(item, dict):
            yield SourceRow(number, None, NOT_AN_OBJECT)
        elif not is_blank_row(item):
            yield SourceRow(number, item)


@ROW_READERS.register(FileFormat.JSONL)
class JsonLinesReader:
    file_format: ClassVar[FileFormat] = FileFormat.JSONL

    @contextmanager
    def open(self, path: Path, options: ReadOptions, limits: ReadLimits) -> Iterator[RowStream]:
        with path.open(encoding="utf-8-sig") as handle:
            yield RowStream(columns=[], rows=_lines(handle), encoding="UTF-8")
