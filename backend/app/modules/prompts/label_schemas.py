"""
Prompt label schemas: labels, their history, the "move on accept" setting and the shape an app
receives when it fetches a prompt by name.

A label name is a short lowercase word (`production`, `staging`, `canary-eu`) so it is safe in a
URL and in a config file. `FetchedPrompt` carries everything an app needs to use the prompt
(templates, variables, default parameters) and nothing that belongs to the workspace.
"""

import re
import uuid
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, Field

LABEL_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,47}$")
LABEL_RULE = "A label is 1 to 48 lowercase letters, digits, dots, dashes or underscores, such as production or staging."


def _valid_label(name: str) -> str:
    name = name.strip().lower()
    if not LABEL_PATTERN.fullmatch(name):
        raise ValueError(LABEL_RULE)
    return name


LabelName = Annotated[str, AfterValidator(_valid_label)]


class MoveReason(StrEnum):
    ASSIGN = "assign"
    ACCEPT = "accept"
    ROLLBACK = "rollback"
    REMOVE = "remove"


class LabelAssign(BaseModel):
    version_id: uuid.UUID


class LabelSettingsUpdate(BaseModel):
    accept_moves_label: LabelName | None = Field(
        default=None,
        description="The label that Accept moves to the accepted version. Leave empty to never move a label.",
    )


class PromptLabelOut(BaseModel):
    name: str
    version_id: uuid.UUID
    version: int
    moved_at: datetime
    can_roll_back: bool


class LabelMoveOut(BaseModel):
    id: uuid.UUID
    label: str
    reason: MoveReason
    from_version: int | None
    to_version: int | None
    moved_by: uuid.UUID | None
    moved_by_name: str | None
    created_at: datetime


class LabelsOut(BaseModel):
    labels: list[PromptLabelOut]
    accept_moves_label: str | None


class FetchedPrompt(BaseModel):
    name: str
    label: str | None
    version: int
    version_id: uuid.UUID
    system_template: str | None
    user_template: str | None
    variables: list[str]
    default_params: dict[str, Any]
    updated_at: datetime
