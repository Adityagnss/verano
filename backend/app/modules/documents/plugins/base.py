"""
The document-extractor contract. An extractor turns one untrusted file into text blocks,
checking the parse deadline as it goes and refusing documents over the page or text
limits. Extractors register in `DOCUMENT_EXTRACTORS` under their `FileFormat`.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Protocol

from app.core.errors import AppError, ValidationFailed
from app.core.files import Deadline, ZipLimits
from app.core.registry import Registry
from app.modules.datasets.schemas import FileFormat
from app.modules.documents.schemas import Block

TOO_MUCH_TEXT = "This document has more than {limit:,} characters of text. Split it into smaller documents."


class UnreadableDocument(AppError):
    status_code = 422
    code = "unreadable_document"


@dataclass(frozen=True)
class DocumentLimits:
    max_pages: int
    max_chars: int
    zip: ZipLimits


class DocumentExtractor(Protocol):
    file_format: ClassVar[FileFormat]

    def extract(self, path: Path, limits: DocumentLimits, deadline: Deadline) -> list[Block]: ...


DOCUMENT_EXTRACTORS: Registry[type[DocumentExtractor]] = Registry("document extractor")


class TextBudget:
    def __init__(self, max_chars: int) -> None:
        self._left = max_chars
        self._limit = max_chars

    def take(self, text: str) -> str:
        self._left -= len(text)
        if self._left < 0:
            raise ValidationFailed(TOO_MUCH_TEXT.format(limit=self._limit))
        return text
