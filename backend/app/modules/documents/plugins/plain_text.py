"""
Plain-text and Markdown extractors. Text is read as UTF-8 (a byte-order mark is
accepted; undecodable bytes are replaced rather than failing the document). In Markdown,
lines starting with `#` are headings; everything else is paragraph text.
"""

from pathlib import Path
from typing import ClassVar

from app.core.files import Deadline
from app.modules.datasets.schemas import FileFormat
from app.modules.documents.plugins.base import DOCUMENT_EXTRACTORS, DocumentLimits, TextBudget
from app.modules.documents.schemas import Block

MARKDOWN_HEADING = "#"


def _read(path: Path, limits: DocumentLimits) -> str:
    budget = TextBudget(limits.max_chars)
    with path.open(encoding="utf-8-sig", errors="replace") as handle:
        return budget.take(handle.read(limits.max_chars + 1))


@DOCUMENT_EXTRACTORS.register(FileFormat.TXT)
class TextExtractor:
    file_format: ClassVar[FileFormat] = FileFormat.TXT

    def extract(self, path: Path, limits: DocumentLimits, deadline: Deadline) -> list[Block]:
        return [Block(text=_read(path, limits))]


@DOCUMENT_EXTRACTORS.register(FileFormat.MD)
class MarkdownExtractor:
    file_format: ClassVar[FileFormat] = FileFormat.MD

    def extract(self, path: Path, limits: DocumentLimits, deadline: Deadline) -> list[Block]:
        blocks: list[Block] = []
        paragraph: list[str] = []
        for line in _read(path, limits).splitlines():
            deadline.check()
            if line.lstrip().startswith(MARKDOWN_HEADING):
                blocks.append(Block(text="\n".join(paragraph)))
                blocks.append(Block(text=line.lstrip().lstrip(MARKDOWN_HEADING).strip(), heading=True))
                paragraph = []
            else:
                paragraph.append(line)
        blocks.append(Block(text="\n".join(paragraph)))
        return blocks
