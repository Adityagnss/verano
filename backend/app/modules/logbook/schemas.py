"""
Logbook schemas: the filters shared by every logbook view, one row per model answer, the
full detail of one answer (with the same case's other answers to compare), the raw model
calls, and the numbers behind the analysis charts.

Nothing here is stored: every value is read from the run, score and call records the app
already keeps, so the logbook can never disagree with Results or the cost totals.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from app.modules.datasets.schemas import ItemSource
from app.modules.engine.schemas import RunStatus
from app.modules.gateway.schemas import CallPurpose, CallStatus


class AnswerFilters(BaseModel):
    experiment_ids: list[uuid.UUID] = []
    prompt_version_ids: list[uuid.UUID] = []
    models: list[str] = []
    providers: list[str] = []
    statuses: list[RunStatus] = []
    sources: list[ItemSource] = []
    categories: list[str] = []
    failed_checks: list[str] = []
    passed: bool | None = None
    run_number: int | None = Field(default=None, ge=1)
    q: str | None = Field(default=None, max_length=200)
    date_from: datetime | None = None
    date_to: datetime | None = None


class AnswerSort(StrEnum):
    TIME = "time"
    EXPERIMENT = "experiment"
    VERSION = "version"
    MODEL = "model"
    CASE = "case"
    PASSED = "passed"
    QUALITY = "quality"
    GOLDEN_MATCH = "golden_match"
    COST = "cost"
    LATENCY = "latency"
    TOKENS = "tokens"


class SortOrder(StrEnum):
    ASC = "asc"
    DESC = "desc"


class AnswerQuery(AnswerFilters):
    """The filters plus sorting and paging: one model, because FastAPI takes a query model
    as the whole query string."""

    sort: AnswerSort = AnswerSort.TIME
    order: SortOrder = SortOrder.DESC
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1, le=500)


class AnswerRow(BaseModel):
    run_id: uuid.UUID
    experiment_id: uuid.UUID
    experiment: str
    created_at: datetime
    prompt_version_id: uuid.UUID
    prompt_version: int
    model: str
    provider: str
    run_number: int
    case_number: int
    source: str
    category: str
    status: RunStatus
    passed: bool | None
    quality: float | None
    golden_match: float | None
    failed_checks: list[str]
    input_preview: str
    golden_answer: str | None
    output_preview: str | None
    error: str | None
    input_tokens: int | None
    output_tokens: int | None
    cost: Decimal | None
    latency_ms: int | None
    temperature: float | None
    max_tokens: int | None
    attempts: int


class AnswerPage(BaseModel):
    items: list[AnswerRow]
    total: int
    offset: int
    limit: int


class ScoreDetail(BaseModel):
    evaluator: str
    value: float
    passed: bool
    required: bool
    weight: float
    reason: str


class SiblingAnswer(BaseModel):
    run_id: uuid.UUID
    model: str
    run_number: int
    output: str | None
    error: str | None
    passed: bool | None
    quality: float | None
    cost: Decimal | None
    latency_ms: int | None


class AnswerDetail(BaseModel):
    row: AnswerRow
    inputs: dict[str, Any]
    golden_answer: str | None
    rubric: list[Any] | None
    output: str | None
    rendered_system_prompt: str | None
    rendered_user_prompt: str | None
    finish_reason: str | None
    params: dict[str, Any]
    scores: list[ScoreDetail]
    siblings: list[SiblingAnswer]


class ExperimentOption(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime
    prompt_version_id: uuid.UUID
    prompt_version: int


class VersionOption(BaseModel):
    id: uuid.UUID
    version: int


class LogOptions(BaseModel):
    experiments: list[ExperimentOption]
    prompt_versions: list[VersionOption]
    models: list[str]
    providers: list[str]
    categories: list[str]
    checks: list[str]


class GroupStats(BaseModel):
    prompt_version: int
    model: str
    answers: int
    passed: int
    pass_rate: float | None
    quality: float | None
    golden_match: float | None
    failed_calls: int
    cost: Decimal | None
    unknown_price_answers: int
    avg_latency_ms: float | None
    p50_latency_ms: float | None
    p90_latency_ms: float | None
    input_tokens: int
    output_tokens: int


class CheckCount(BaseModel):
    check: str
    failures: int


class Totals(BaseModel):
    answers: int
    experiments: int
    models: int
    passed: int
    failed_calls: int
    cost: Decimal | None
    unknown_price_answers: int
    input_tokens: int
    output_tokens: int


class AnalysisOut(BaseModel):
    totals: Totals
    groups: list[GroupStats]
    failed_checks: list[CheckCount]


class CallFilters(BaseModel):
    experiment_ids: list[uuid.UUID] = []
    purposes: list[CallPurpose] = []
    statuses: list[CallStatus] = []
    models: list[str] = []
    providers: list[str] = []
    q: str | None = Field(default=None, max_length=200)
    date_from: datetime | None = None
    date_to: datetime | None = None


class CallQuery(CallFilters):
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1, le=500)


class CallRow(BaseModel):
    id: uuid.UUID
    created_at: datetime
    purpose: CallPurpose
    status: CallStatus
    provider: str
    model: str
    experiment_id: uuid.UUID | None
    experiment: str | None
    step: str | None
    input_tokens: int | None
    output_tokens: int | None
    cost: Decimal | None
    latency_ms: int | None
    ttft_ms: int | None
    attempts: int
    error: str | None
    request_preview: str
    response_preview: str | None


class CallPage(BaseModel):
    items: list[CallRow]
    total: int
    offset: int
    limit: int


class CallDetail(BaseModel):
    row: CallRow
    params: dict[str, Any]
    labels: dict[str, Any]
    request_messages: list[Any]
    output_text: str | None
    finish_reason: str | None
    trace_id: str
