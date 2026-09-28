"""
CSV / TSV reader.

Real exports are rarely clean UTF-8, so the encoding is detected, not assumed: a UTF-8 or
UTF-16 byte-order mark wins; otherwise the whole file is checked as UTF-8 (streaming, in
1 MB chunks); if that fails it is read as Windows-1252, what Excel on Windows writes. The
detected encoding is reported so the user can correct it. The delimiter (comma,
semicolon, tab or pipe) is sniffed from the first 64 KB, since Excel in many locales
saves with semicolons. Rows are numbered like a spreadsheet: the header is row 1.
Cells are capped in size (`csv_field_max_chars`), so one huge field can't exhaust memory.
"""

import codecs
import csv
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import ClassVar

from app.modules.datasets.domain import SourceRow, clean_header, is_blank
from app.modules.datasets.plugins.importers.base import (
    ROW_READERS,
    ReadLimits,
    ReadOptions,
    RowStream,
    UnreadableFile,
    is_blank_row,
)
from app.modules.datasets.schemas import FileFormat

BOMS: list[tuple[bytes, str, str]] = [
    (codecs.BOM_UTF8, "utf-8-sig", "UTF-8 (with BOM)"),
    (codecs.BOM_UTF16_LE, "utf-16", "UTF-16 (with BOM)"),
    (codecs.BOM_UTF16_BE, "utf-16", "UTF-16 (with BOM)"),
]
FALLBACKS: list[tuple[str, str]] = [("utf-8", "UTF-8"), ("cp1252", "Windows-1252")]
CHUNK = 1024 * 1024
SNIFF_CHARS = 64 * 1024
DELIMITERS = ",;\t|"
EXTRA_CELLS = "This row has more cells than the header"
UNKNOWN_ENCODING = "This file's text encoding couldn't be recognised. Save it as UTF-8 CSV and upload it again."


def _decodes_as(path: Path, codec: str) -> bool:
    decoder = codecs.getincrementaldecoder(codec)()
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(CHUNK):
                decoder.decode(chunk)
            decoder.decode(b"", final=True)
    except UnicodeDecodeError:
        return False
    return True


def detect_encoding(path: Path) -> tuple[str, str]:
    with path.open("rb") as handle:
        head = handle.read(4)
    for bom, codec, label in BOMS:
        if head.startswith(bom):
            return codec, label
    for codec, label in FALLBACKS:
        if _decodes_as(path, codec):
            return codec, label
    raise UnreadableFile(UNKNOWN_ENCODING)


def _delimiter(sample: str) -> str:
    try:
        return csv.Sniffer().sniff(sample, delimiters=DELIMITERS).delimiter
    except csv.Error:
        return ","


@ROW_READERS.register(FileFormat.CSV)
class CsvReader:
    file_format: ClassVar[FileFormat] = FileFormat.CSV

    @contextmanager
    def open(self, path: Path, options: ReadOptions, limits: ReadLimits) -> Iterator[RowStream]:
        csv.field_size_limit(limits.field_max_chars)
        codec, label = detect_encoding(path)
        with path.open(encoding=codec, newline="") as handle:
            delimiter = _delimiter(handle.read(SNIFF_CHARS))
            handle.seek(0)
            reader = csv.reader(handle, delimiter=delimiter)
            header = clean_header(next(reader, []))
            yield RowStream(
                columns=header,
                rows=self._rows(reader, header),
                encoding=label,
                delimiter=delimiter,
            )

    @staticmethod
    def _rows(reader: Iterator[list[str]], header: list[str]) -> Iterator[SourceRow]:
        number = 1
        try:
            for number, cells in enumerate(reader, start=2):
                values = dict(zip(header, cells, strict=False))
                if len(cells) > len(header) and not all(is_blank(cell) for cell in cells[len(header) :]):
                    yield SourceRow(number, None, EXTRA_CELLS)
                elif values and not is_blank_row(values):
                    yield SourceRow(number, values)
        except csv.Error as exc:
            raise UnreadableFile(f"This CSV file is damaged after row {number}: {exc}") from exc
