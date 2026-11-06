"""
Schemas for generating conversation cases (ADR 0039): the request, what the model must return, and the result.

A conversation case is the input the simulated user of an app in conversation mode plays from (ADR 0027): a persona,
a goal, an opening message, the situation, and the condition that ends the conversation.
"""

import uuid

from pydantic import BaseModel, Field

from app.modules.generator.schemas import CaseCategory, GeneratorModel


class ConversationCasesRequest(BaseModel):
    count: int | None = Field(default=None, ge=1, description="How many cases; the default comes from settings.")
    prompt_version_id: uuid.UUID | None = None
    generator: GeneratorModel | None = None
    focus: str | None = Field(default=None, max_length=500, description="What the cases should concentrate on.")


class GeneratedConversationCase(BaseModel):
    persona: str = Field(min_length=3, max_length=400)
    goal: str = Field(min_length=3, max_length=400)
    opening: str = Field(min_length=1, max_length=1000)
    stop_when: str = Field(min_length=3, max_length=400)
    scenario: str | None = Field(default=None, max_length=600)
    category: CaseCategory = CaseCategory.HAPPY_PATH
    max_turns: int | None = Field(default=None, ge=1, le=100)


class GeneratedConversationBatch(BaseModel):
    cases: list[GeneratedConversationCase]


class ConversationCasesOut(BaseModel):
    dataset_version_id: uuid.UUID
    added: int
    dropped_duplicates: int
    dropped_invalid: int
    generator_model: str
    message: str
