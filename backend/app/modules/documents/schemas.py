"""Reference-document schemas: extracted text blocks and the sections stored for grounding."""

import uuid

from pydantic import BaseModel, ConfigDict


class Block(BaseModel):
    text: str
    heading: bool = False


class SectionDraft(BaseModel):
    title: str | None
    text: str


class SectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    input_file_id: uuid.UUID
    position: int
    title: str | None
    text: str
    char_count: int
