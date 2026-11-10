"""
Security schemas: the attack families, a pack and its draft cases, the run request, the report with per-category
pass rates, the gate answer for `--ci`, and what "harden" starts.
"""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.modules.engine.schemas import ModelRun
from app.modules.evaluation.schemas import JudgeChoice


class PackStatus(StrEnum):
    GENERATING = "generating"
    DRAFT = "draft"
    APPROVED = "approved"
    FAILED = "failed"


class CaseStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    REJECTED = "rejected"


class AttackFamilyOut(BaseModel):
    id: str
    title: str
    owasp: str
    description: str
    safe_behaviour: str
    needs_tools: bool
    built_in_cases: int


class GeneratorChoice(BaseModel):
    credential_id: uuid.UUID
    model: str


class PackCreate(BaseModel):
    prompt_version_id: uuid.UUID
    name: str | None = Field(default=None, max_length=200)
    # left out: every family except the tool one (which is added when `tool_app` is on)
    categories: list[str] | None = None
    per_category: int | None = Field(default=None, ge=1)
    tool_app: bool = False
    # a model that writes extra attacks tailored to the app; left out, only the built-in attacks are used (no cost)
    generator: GeneratorChoice | None = None
    # an existing canary to keep using (the same marker is already in the prompt); left out, a new one is made
    canary: str | None = Field(default=None, min_length=6, max_length=64)


class CaseOut(BaseModel):
    id: uuid.UUID
    pack_id: uuid.UUID
    category: str
    attack: str
    inputs: dict[str, Any]
    safe_behaviour: str
    source: str
    status: CaseStatus


class CaseUpdate(BaseModel):
    attack: str | None = Field(default=None, min_length=1, max_length=20_000)
    safe_behaviour: str | None = Field(default=None, min_length=1, max_length=4_000)
    status: CaseStatus | None = None


class BulkReview(BaseModel):
    category: str | None = None
    status: CaseStatus = CaseStatus.APPROVED


class CategoryCount(BaseModel):
    category: str
    title: str
    owasp: str
    draft: int
    approved: int
    rejected: int


class PackOut(BaseModel):
    id: uuid.UUID
    prompt_version_id: uuid.UUID
    name: str
    status: PackStatus
    message: str | None
    canary: str
    categories: list[str]
    per_category: int
    tool_app: bool
    dataset_version_id: uuid.UUID | None
    counts: list[CategoryCount]
    canary_in_prompt: bool
    created_at: datetime


class PackDetail(PackOut):
    cases: list[CaseOut]


class SecurityRunRequest(BaseModel):
    models: list[ModelRun] = Field(min_length=1)
    # the model that judges whether each answer behaved safely (required: the safe-behaviour check is judged)
    judge: JudgeChoice
    budget_cap: float | None = Field(default=None, gt=0)
    prompt_version_id: uuid.UUID | None = None
    prompt_id: uuid.UUID | None = None


class CategoryResult(BaseModel):
    category: str
    title: str
    owasp: str
    answers: int
    resisted: int
    pass_rate: float | None
    earlier_pass_rate: float | None
    failing_examples: list[str]


class SecurityReport(BaseModel):
    pack_id: uuid.UUID
    experiment_id: uuid.UUID
    experiment_status: str
    canary_in_prompt: bool
    overall_pass_rate: float | None
    categories: list[CategoryResult]
    notes: list[str]


class GateFailureOut(BaseModel):
    category: str
    message: str


class GateOut(BaseModel):
    passed: bool
    experiment_id: uuid.UUID
    min_pass_rate: float
    max_drop: float | None
    failures: list[GateFailureOut]
    categories: list[CategoryResult]


class HardenRequest(BaseModel):
    experiment_id: uuid.UUID
    writer: JudgeChoice | None = None
    rounds: int | None = Field(default=None, ge=1, le=6)


class GuardRequest(BaseModel):
    """One piece of text to screen: what a user will send (`input`) or what the app will show (`output`)."""

    text: str = Field(min_length=1, max_length=50_000)
    direction: Literal["input", "output"]
    # output only: the canary planted in the prompt, and hidden instructions that must not be repeated
    canary: str | None = Field(default=None, min_length=6, max_length=64)
    secrets: list[str] = Field(default_factory=list, max_length=10)
    # personal data is always looked for in an output; in an input only when this is on
    pii_in_input: bool = False


class GuardFindingOut(BaseModel):
    check: str
    family: str
    detail: str


class GuardOut(BaseModel):
    allowed: bool
    findings: list[GuardFindingOut]
    note: str
