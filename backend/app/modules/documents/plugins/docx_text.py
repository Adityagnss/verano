"""
Word (.docx) extractor (python-docx). A DOCX is a zip of XML parts, so it passes the
zip-bomb check before it is opened; python-docx parses with entity resolution turned off.
Paragraphs styled as headings become section headings; tables become one line per row
with cells separated by " | ".
"""

import zipfile
from pathlib import Path
from typing import ClassVar

import docx
from docx.opc.exceptions import PackageNotFoundError

from app.core.files import ZIP_SIGNATURE, Deadline, check_magic, check_zip
from app.modules.datasets.schemas import FileFormat
from app.modules.documents.plugins.base import (
    DOCUMENT_EXTRACTORS,
    DocumentLimits,
    TextBudget,
    UnreadableDocument,
)
from app.modules.documents.schemas import Block

LABEL = "Word"
HEADING_STYLE = "heading"
TITLE_STYLE = "title"
CELL_SEPARATOR = " | "
DAMAGED = "This Word file is damaged and can't be opened. Save it again from Word and re-upload."


def _is_heading(style_name: str | None) -> bool:
    name = (style_name or "").lower()
    return name.startswith(HEADING_STYLE) or name == TITLE_STYLE


@DOCUMENT_EXTRACTORS.register(FileFormat.DOCX)
class DocxExtractor:
    file_format: ClassVar[FileFormat] = FileFormat.DOCX

    def extract(self, path: Path, limits: DocumentLimits, deadline: Deadline) -> list[Block]:
        check_magic(path, ZIP_SIGNATURE, LABEL)
        check_zip(path, limits.zip, LABEL)
        try:
            document = docx.Document(str(path))
        except (PackageNotFoundError, zipfile.BadZipFile, KeyError, ValueError) as exc:
            raise UnreadableDocument(DAMAGED) from exc
        budget = TextBudget(limits.max_chars)
        blocks: list[Block] = []
        for paragraph in document.paragraphs:
            deadline.check()
            if paragraph.text.strip():
                style = paragraph.style.name if paragraph.style is not None else None
                blocks.append(Block(text=budget.take(paragraph.text), heading=_is_heading(style)))
        for table in document.tables:
            deadline.check()
            rows = [CELL_SEPARATOR.join(cell.text.strip() for cell in row.cells) for row in table.rows]
            blocks.append(Block(text=budget.take("\n".join(rows))))
        return blocks
