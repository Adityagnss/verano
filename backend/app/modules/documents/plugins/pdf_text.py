"""
PDF extractor (pypdf). The file must carry the PDF signature; encrypted PDFs and PDFs over
the page limit are refused before any page is read. Each page's text becomes blocks under
a "Page N" heading, so sections can cite where they came from. pypdf also caps every
decompressed stream (75 MB by default), which blocks compressed-stream bombs.
"""

from pathlib import Path
from typing import ClassVar

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.core.errors import ValidationFailed
from app.core.files import Deadline, check_magic
from app.modules.datasets.schemas import FileFormat
from app.modules.documents.plugins.base import (
    DOCUMENT_EXTRACTORS,
    DocumentLimits,
    TextBudget,
    UnreadableDocument,
)
from app.modules.documents.schemas import Block

SIGNATURE = b"%PDF-"
LABEL = "PDF"
TOO_MANY_PAGES = "This PDF has {pages:,} pages; the limit is {limit:,}. Split it into smaller documents."
ENCRYPTED = "This PDF is password-protected. Save an unprotected copy and upload that."
DAMAGED = "This PDF is damaged and can't be read. Save it again from its app and re-upload."
PAGE_TITLE = "Page {number}"


@DOCUMENT_EXTRACTORS.register(FileFormat.PDF)
class PdfExtractor:
    file_format: ClassVar[FileFormat] = FileFormat.PDF

    def extract(self, path: Path, limits: DocumentLimits, deadline: Deadline) -> list[Block]:
        check_magic(path, SIGNATURE, LABEL)
        try:
            reader = PdfReader(path, strict=False)
            if reader.is_encrypted:
                raise UnreadableDocument(ENCRYPTED)
            pages = len(reader.pages)
            if pages > limits.max_pages:
                raise ValidationFailed(TOO_MANY_PAGES.format(pages=pages, limit=limits.max_pages))
            budget = TextBudget(limits.max_chars)
            blocks: list[Block] = []
            for number, page in enumerate(reader.pages, start=1):
                deadline.check()
                text = budget.take(page.extract_text() or "")
                blocks += [Block(text=PAGE_TITLE.format(number=number), heading=True), Block(text=text)]
            return blocks
        except PdfReadError as exc:
            raise UnreadableDocument(DAMAGED) from exc
