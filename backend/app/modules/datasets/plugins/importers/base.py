"""
The row-reader contract and the shared profiling pass.

A reader opens one rows file and yields `SourceRow`s lazily, one at a time, so no file is
ever loaded whole into memory. The profiling pass is one streaming pass to learn what the user
needs for mapping: the columns (the header, or for JSON the union of keys in first-seen
order), a few sample rows, and the row count, refusing files over the row limit. Readers
register in `ROW_READERS` under their `FileFormat`. `ProfileBuilder` accumulates the profile
one row at a time, so the caller can check the deadline and report progress as it goes.
"""

from collections.abc import Iterator
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Protocol

from app.core.errors import AppError, ValidationFailed
from app.core.files import ZipLimits
from app.core.registry import Registry
from app.modules.datasets.domain import SourceRow, is_blank
from app.modules.datasets.schemas import FileFormat, FileProfile

TOO_MANY_ROWS = "This file has more than {limit:,} rows. Split it into smaller files."


class UnreadableFile(AppError):
    status_code = 422
    code = "unreadable_file"


@dataclass(frozen=True)
class ReadLimits:
    max_rows: int
    field_max_chars: int
    zip: ZipLimits
    sample_rows: int


@dataclass(frozen=True)
class ReadOptions:
    sheet: str | None = None


@dataclass
class RowStream:
    columns: list[str]
    rows: Iterator[SourceRow]
    sheets: list[str] = field(default_factory=list)
    sheet: str | None = None
    encoding: str | None = None
    delimiter: str | None = None
    warnings: list[str] = field(default_factory=list)


class RowReader(Protocol):
    file_format: ClassVar[FileFormat]

    def open(self, path: Path, options: ReadOptions, limits: ReadLimits) -> AbstractContextManager[RowStream]: ...


ROW_READERS: Registry[type[RowReader]] = Registry("rows reader")


def is_blank_row(values: dict[str, Any]) -> bool:
    return all(is_blank(value) for value in values.values())


class ProfileBuilder:
    def __init__(self, stream: RowStream, limits: ReadLimits) -> None:
        self._stream = stream
        self._limits = limits
        self._columns = dict.fromkeys(stream.columns)
        self._samples: list[dict[str, Any]] = []
        self.count = 0

    def add(self, row: SourceRow) -> None:
        self.count += 1
        if self.count > self._limits.max_rows:
            raise ValidationFailed(TOO_MANY_ROWS.format(limit=self._limits.max_rows))
        if row.values is not None:
            self._columns.update(dict.fromkeys(row.values))
            if len(self._samples) < self._limits.sample_rows:
                self._samples.append(row.values)

    def build(self, file_format: FileFormat) -> FileProfile:
        stream = self._stream
        return FileProfile(
            format=file_format,
            columns=list(self._columns),
            sheets=stream.sheets,
            sheet=stream.sheet,
            encoding=stream.encoding,
            delimiter=stream.delimiter,
            row_count=self.count,
            sample_rows=self._samples,
            warnings=stream.warnings,
        )
