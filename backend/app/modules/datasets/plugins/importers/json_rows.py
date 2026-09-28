"""
JSON reader: a top-level array of objects, streamed item by item with ijson (C backend),
so a large file is never parsed into memory at once. Anything else at the top level gets a
clear message pointing to JSON Lines. Items are numbered from 1; an item that isn't an
object is reported as an invalid row. Numbers come back as ints and floats, not Decimals.
"""

import codecs
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO, ClassVar

import ijson

from app.modules.datasets.domain import SourceRow
from app.modules.datasets.plugins.importers.base import (
    ROW_READERS,
    ReadLimits,
    ReadOptions,
    RowStream,
    UnreadableFile,
    is_blank_row,
)
from app.modules.datasets.schemas import FileFormat

NOT_A_LIST = (
    "A JSON file must be a list of objects, like [{...}, {...}]. For one object per line, save it as .jsonl instead."
)
NOT_AN_OBJECT = "This item isn't an object with named fields"
DAMAGED = "This JSON file isn't valid JSON (the problem is after item {item}): {detail}"
PEEK_BYTES = 4096


def _starts_with_list(handle: BinaryIO) -> bool:
    head = handle.read(PEEK_BYTES).removeprefix(codecs.BOM_UTF8).lstrip()
    handle.seek(0)
    return head.startswith(b"[")


def _items(handle: BinaryIO) -> Iterator[SourceRow]:
    number = 0
    try:
        for number, item in enumerate(ijson.items(handle, "item", use_float=True), start=1):
            if not isinstance(item, dict):
                yield SourceRow(number, None, NOT_AN_OBJECT)
            elif not is_blank_row(item):
                yield SourceRow(number, item)
    except ijson.JSONError as exc:
        raise UnreadableFile(DAMAGED.format(item=number, detail=exc)) from exc


@ROW_READERS.register(FileFormat.JSON)
class JsonReader:
    file_format: ClassVar[FileFormat] = FileFormat.JSON

    @contextmanager
    def open(self, path: Path, options: ReadOptions, limits: ReadLimits) -> Iterator[RowStream]:
        with path.open("rb") as handle:
            if not _starts_with_list(handle):
                raise UnreadableFile(NOT_A_LIST)
            if handle.read(3) != codecs.BOM_UTF8:
                handle.seek(0)
            yield RowStream(columns=[], rows=_items(handle), encoding="UTF-8")
