"""Schemas for "update checks to the current default set" (ADR 0039): the preview and what applying it returns."""

import uuid

from pydantic import BaseModel, Field

from app.modules.evaluation.schemas import EvaluatorSetVersionOut
from app.modules.generator.defaults_update import Action


class DifferenceOut(BaseModel):
    field: str
    before: str | None
    after: str | None


class CheckLineOut(BaseModel):
    name: str
    action: Action
    # A check from the default family that the user changed: it is only removed when named in `remove`
    edited: bool
    differences: list[DifferenceOut]
    note: str


class DefaultsPreviewOut(BaseModel):
    evaluator_set_version_id: uuid.UUID
    task_type: str
    up_to_date: bool
    summary: str
    lines: list[CheckLineOut]


class DefaultsApply(BaseModel):
    """Apply the update. `skip` names changes or additions to leave out; `remove` names the checks to remove
    (nothing is removed unless it is named here)."""

    skip: list[str] = Field(default=[], max_length=100)
    remove: list[str] = Field(default=[], max_length=100)


class DefaultsApplied(BaseModel):
    version: EvaluatorSetVersionOut
    note: str
    created: bool
