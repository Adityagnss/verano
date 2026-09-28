"""
Pure sectioning of extracted document text.

Extractors produce blocks (headings and paragraphs). `split_sections` starts a new
section at each heading, keeps the heading as the section title, and cuts long sections
into chunks of at most `max_chars` on paragraph boundaries (a single paragraph longer
than the limit is cut on sentence, then on character boundaries). Sections are the unit a
generated test case is grounded in and cites as its context, so they are sized to fit
comfortably in a prompt. Empty sections are dropped. No I/O.
"""

import re

from app.modules.documents.schemas import Block, SectionDraft

PARAGRAPHS = re.compile(r"\n\s*\n")
SENTENCES = re.compile(r"(?<=[.!?])\s+")


def _pieces(paragraph: str, max_chars: int) -> list[str]:
    if len(paragraph) <= max_chars:
        return [paragraph]
    pieces: list[str] = []
    current = ""
    for sentence in SENTENCES.split(paragraph):
        while len(sentence) > max_chars:
            pieces.extend([current] if current else [])
            current = ""
            pieces.append(sentence[:max_chars])
            sentence = sentence[max_chars:]
        joined = f"{current} {sentence}".strip()
        if len(joined) > max_chars:
            pieces.append(current)
            joined = sentence
        current = joined
    return [piece for piece in [*pieces, current] if piece.strip()]


def chunk_text(text: str, max_chars: int) -> list[str]:
    chunks: list[str] = []
    current = ""
    for paragraph in (p.strip() for p in PARAGRAPHS.split(text)):
        for piece in _pieces(paragraph, max_chars) if paragraph else []:
            joined = f"{current}\n\n{piece}" if current else piece
            if len(joined) > max_chars:
                chunks.append(current)
                joined = piece
            current = joined
    return [chunk for chunk in [*chunks, current] if chunk.strip()]


def split_sections(blocks: list[Block], max_chars: int) -> list[SectionDraft]:
    sections: list[SectionDraft] = []
    title: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        sections.extend(SectionDraft(title=title, text=chunk) for chunk in chunk_text("\n\n".join(buffer), max_chars))

    for block in blocks:
        if block.heading:
            flush()
            title, buffer = block.text.strip() or None, []
        else:
            buffer.append(block.text)
    flush()
    return sections
