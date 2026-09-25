"""
The document_sections table.

A reference document (an `input_files` row of kind reference_document) is extracted to
text and split into ordered sections; generation is grounded in sections and dataset
items cite them as `context` so evaluators can check faithfulness against the source.
"""

import uuid

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, CreatedAtMixin, IdMixin


class DocumentSection(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "document_sections"
    __table_args__ = (Index(None, "input_file_id", "position", unique=True),)

    input_file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("input_files.id", ondelete="CASCADE"))
    position: Mapped[int]
    title: Mapped[str | None] = mapped_column(String(500))
    text: Mapped[str] = mapped_column(Text)
    char_count: Mapped[int]
