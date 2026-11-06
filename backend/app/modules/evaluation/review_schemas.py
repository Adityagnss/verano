"""Review queue schemas (ADR 0038): assigning answers to people, their queue and progress, and disagreements."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.modules.evaluation.schemas import LabelSummary, LabelVerdict, ScoreOut

NEEDS_ONE_WAY = "Name the answers to assign, or say how many to pick, but not both."


class QueueStatus(StrEnum):
    OPEN = "open"
    DONE = "done"
    ALL = "all"


class AssignRequest(BaseModel):
    """Give answers to someone to label. Name the answers, or let the server pick `count` of them."""

    experiment_id: uuid.UUID
    assignee_user_id: uuid.UUID | None = Field(default=None, description="Who labels them; you, when left out.")
    test_case_run_ids: list[uuid.UUID] | None = Field(default=None, min_length=1)
    count: int | None = Field(default=None, ge=1, description="How many answers to pick.")
    pick: Literal["unlabelled", "disputed"] = Field(
        default="unlabelled",
        description="Which answers to pick: ones nobody has labelled yet, or ones whose labels disagree.",
    )
    blind: bool = Field(default=False, description="Hide the judge's scores and verdicts while they label.")
    batch_label: str | None = Field(default=None, max_length=120, description='A name for the batch, e.g. "Tuesday".')

    @model_validator(mode="after")
    def _one_way(self) -> "AssignRequest":
        if (self.test_case_run_ids is None) == (self.count is None):
            raise ValueError(NEEDS_ONE_WAY)
        return self


class AssignOut(BaseModel):
    assignee_user_id: uuid.UUID
    assigned: int
    already_assigned: int
    skipped: int = 0  # picked answers the person had already labelled
    message: str


class ReviewJudgeOut(BaseModel):
    """The judge's side of an answer. Never present in a blind review."""

    passed: bool | None
    quality: float | None
    scores: list[ScoreOut]


class ResolutionOut(BaseModel):
    verdict: LabelVerdict
    note: str | None
    resolved_by: uuid.UUID | None
    updated_at: datetime


class ReviewItemOut(BaseModel):
    assignment_id: uuid.UUID
    experiment_id: uuid.UUID
    experiment_name: str
    test_case_run_id: uuid.UUID
    assigned_at: datetime
    batch_label: str | None
    blind: bool
    done: bool
    inputs: dict[str, Any]
    expected_output: str | None
    rubric: list[Any] | None
    output: str | None
    truncated: bool
    model: str
    retrieved_chunks: list[Any] | None
    tool_calls: list[Any] | None
    my_label: LabelVerdict | None
    my_note: str | None
    judge: ReviewJudgeOut | None  # None in a blind review
    labels: LabelSummary | None  # what everyone said; None in a blind review
    resolution: ResolutionOut | None  # None in a blind review
    hidden: bool  # blind review: the judge's fields and other people's labels are left out of this response


class QueueOut(BaseModel):
    items: list[ReviewItemOut]
    next_cursor: str | None
    open: int  # how many answers are still waiting for this person, over the whole queue
    done: int


class PersonProgress(BaseModel):
    user_id: uuid.UUID
    name: str
    assigned: int
    done: int
    open: int


class ProgressOut(BaseModel):
    people: list[PersonProgress]
    assigned: int
    done: int
    open: int
    disputed: int  # answers whose labels disagree and have no final verdict yet
    resolved: int


class MemberOut(BaseModel):
    user_id: uuid.UUID
    name: str
    email: str
    is_owner: bool


class PersonLabel(BaseModel):
    user_id: uuid.UUID
    name: str
    verdict: LabelVerdict
    note: str | None


class DisputeOut(BaseModel):
    experiment_id: uuid.UUID
    test_case_run_id: uuid.UUID
    inputs: dict[str, Any]
    expected_output: str | None
    output: str | None
    labels: list[PersonLabel]
    resolution: ResolutionOut | None


class ResolveRequest(BaseModel):
    verdict: LabelVerdict
    note: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _final(self) -> "ResolveRequest":
        if self.verdict is LabelVerdict.UNSURE:
            raise ValueError("A final verdict is good or bad. Use a note to explain a hard call.")
        return self
