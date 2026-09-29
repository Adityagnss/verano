"""
Prompt Studio schemas: prompts, immutable versions, the three prompt shapes, rendering and
validation results.

A version holds a system template, a user template, or both. `PromptShape` names which,
because it decides how a test case becomes messages: with a user template the case's
values fill its `{{variables}}`; with only a system template the case's
`USER_MESSAGE_INPUT` value is sent as the user message (the "User message input" mapping
target in the data step).
An input file reaches the prompt as `ATTACHMENT_INPUT`: it fills `{{attachment}}` when the
template uses it, is the user message when there is only a system template, and is
appended to the user message otherwise (DEVELOPMENT.md 2.2).
"""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.gateway.schemas import Message

USER_MESSAGE_INPUT = "user_message"
ATTACHMENT_INPUT = "attachment"


class PromptSource(StrEnum):
    MANUAL = "manual"
    ASSISTANT = "assistant"


class PromptShape(StrEnum):
    SYSTEM_AND_USER = "system_and_user"
    SYSTEM_ONLY = "system_only"
    USER_ONLY = "user_only"


class PromptTemplates(BaseModel):
    system_template: str | None = None
    user_template: str | None = None

    @model_validator(mode="after")
    def _at_least_one(self) -> "PromptTemplates":
        self.system_template = self.system_template or None
        self.user_template = self.user_template or None
        if self.system_template is None and self.user_template is None:
            raise ValueError("Write a system prompt, a user prompt, or both.")
        return self


class PromptCreate(PromptTemplates):
    name: str = Field(min_length=1, max_length=200)
    default_params: dict[str, Any] = {}
    change_reason: str | None = Field(default=None, max_length=2000)


class PromptVersionCreate(PromptTemplates):
    default_params: dict[str, Any] = {}
    change_reason: str | None = Field(default=None, max_length=2000)
    parent_version_id: uuid.UUID | None = None


class PromptVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    prompt_id: uuid.UUID
    version: int
    parent_version_id: uuid.UUID | None
    system_template: str | None
    user_template: str | None
    variables: list[str]
    default_params: dict[str, Any]
    source: PromptSource
    change_reason: str | None
    shape: PromptShape
    required_inputs: list[str]
    created_at: datetime


class PromptOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    created_at: datetime
    latest_version: PromptVersionOut


class RenderRequest(BaseModel):
    inputs: dict[str, Any]


class RenderedPrompt(BaseModel):
    shape: PromptShape
    messages: list[Message]


class ContextFit(BaseModel):
    model_profile_id: uuid.UUID
    display_name: str
    context_window: int | None
    estimated_tokens: int
    fits: bool | None


class PromptCheck(BaseModel):
    shape: PromptShape
    variables: list[str]
    required_inputs: list[str]
    missing_inputs: list[str]
    context: list[ContextFit]
    ok: bool


class InspectRequest(PromptTemplates):
    columns: list[str] | None = None
    sample_inputs: dict[str, Any] | None = None
    model_profile_ids: list[uuid.UUID] | None = None
    max_tokens: int | None = Field(default=None, ge=1)


class CheckRequest(BaseModel):
    columns: list[str] | None = None
    sample_inputs: dict[str, Any] | None = None
    model_profile_ids: list[uuid.UUID] | None = None


class InspectOut(BaseModel):
    check: PromptCheck
    preview: RenderedPrompt | None
