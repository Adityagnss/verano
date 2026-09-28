"""
Excel (.xlsx) reader.

An XLSX file is a zip of XML parts, so it is checked before anything is decompressed: it
must really be a zip, and its parts must pass the zip-bomb limits. openpyxl then reads it in
read-only mode (rows stream from the sheet XML, never the whole workbook), and it parses
through defusedxml, which refuses entity-expansion attacks; those surface as a clear
"unsafe XML" error, whether raised on open or while streaming rows. The user picks the
sheet when there are several; rows are numbered as Excel shows them (header = row 1).
Dates and times become ISO strings, so every value is JSON-safe.
"""

import datetime as dt
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, ClassVar

from defusedxml import DefusedXmlException
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from app.core.errors import ValidationFailed
from app.core.files import ZIP_SIGNATURE, UnsafeFile, check_magic, check_zip
from app.modules.datasets.domain import SourceRow, clean_header
from app.modules.datasets.plugins.importers.base import ROW_READERS, ReadLimits, ReadOptions, RowStream, is_blank_row
from app.modules.datasets.schemas import FileFormat

LABEL = "Excel"
UNSAFE_XML = "This Excel file contains unsafe XML (for example an entity-expansion attack), so it wasn't opened."
DAMAGED = "This Excel file is damaged and can't be opened. Save it again from Excel and re-upload."
UNKNOWN_SHEET = "There is no sheet named '{sheet}' in this file."
TEMPORAL = (dt.datetime, dt.date, dt.time)


def _cell(value: Any) -> Any:
    return value.isoformat() if isinstance(value, TEMPORAL) else value


def _guarded(rows: Iterator[tuple[Any, ...]], header: list[str]) -> Iterator[SourceRow]:
    try:
        for number, cells in enumerate(rows, start=2):
            values = {name: _cell(cell) for name, cell in zip(header, cells, strict=False)}
            if values and not is_blank_row(values):
                yield SourceRow(number, values)
    except DefusedXmlException as exc:
        raise UnsafeFile(UNSAFE_XML) from exc


@ROW_READERS.register(FileFormat.XLSX)
class XlsxReader:
    file_format: ClassVar[FileFormat] = FileFormat.XLSX

    @contextmanager
    def open(self, path: Path, options: ReadOptions, limits: ReadLimits) -> Iterator[RowStream]:
        check_magic(path, ZIP_SIGNATURE, LABEL)
        check_zip(path, limits.zip, LABEL)
        try:
            workbook = load_workbook(path, read_only=True, data_only=True)
        except DefusedXmlException as exc:
            raise UnsafeFile(UNSAFE_XML) from exc
        except (InvalidFileException, zipfile.BadZipFile, KeyError, ValueError) as exc:
            raise UnsafeFile(DAMAGED) from exc
        try:
            sheets = list(workbook.sheetnames)
            sheet = options.sheet or (workbook.active.title if workbook.active else sheets[0])
            if sheet not in sheets:
                raise ValidationFailed(UNKNOWN_SHEET.format(sheet=sheet))
            rows = workbook[sheet].iter_rows(values_only=True)
            try:
                header = clean_header(list(next(rows, ())))
            except DefusedXmlException as exc:
                raise UnsafeFile(UNSAFE_XML) from exc
            yield RowStream(columns=header, rows=_guarded(rows, header), sheets=sheets, sheet=sheet)
        finally:
            workbook.close()
