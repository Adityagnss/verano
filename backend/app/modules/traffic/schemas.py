"""
Traffic schemas: what comes in and out of the traffic, online scoring and alert endpoints.

Texts shown in the list are previews; the full text (up to its size cap) is in the detail view. Tokens, webhook
addresses and email addresses are accepted once and never returned in full.
"""

import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.modules.traffic.domain import pattern_problem


class TraceStatus(StrEnum):
    OK = "ok"
    ERROR = "error"


class ScoreState(StrEnum):
    NEW = "new"
    QUEUED = "queued"
    SCORED = "scored"
    SAMPLED_OUT = "sampled_out"
    NO_CHECKS = "no_checks"


class AlertKind(StrEnum):
    THRESHOLD = "threshold"
    DROP = "drop"


class AlertMetric(StrEnum):
    PASS_RATE = "pass_rate"
    SUCCESS_RATE = "success_rate"


class ChannelKind(StrEnum):
    WEBHOOK = "webhook"
    SLACK = "slack"
    EMAIL = "email"


class AlertStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"


# ----------------------------------------------------------------------------------------------- import


class FormatOut(BaseModel):
    name: str
    label: str
    hint: str


class ProblemOut(BaseModel):
    record: int
    message: str


class ImportReport(BaseModel):
    format: str
    format_label: str
    found: int
    imported: int
    duplicates: int
    ignored: int
    truncated: int
    scrubbed: int
    problems: list[ProblemOut]
    more_problems: int


# ----------------------------------------------------------------------------------------------- traces


class TraceSummary(BaseModel):
    id: uuid.UUID
    source: str
    started_at: datetime
    input_preview: str
    output_preview: str
    status: TraceStatus
    latency_ms: int | None
    model: str | None
    prompt_version: str | None
    rating: float | None
    quality: float | None
    passed: bool | None
    score_state: ScoreState
    input_truncated: bool
    output_truncated: bool
    scrubbed_count: int
    case_made: bool


class TraceScoreOut(BaseModel):
    evaluator_name: str
    value: float
    passed: bool
    judged: bool
    reason: str


class TraceOut(TraceSummary):
    input_text: str
    output_text: str
    error_message: str | None
    tokens_in: int | None
    tokens_out: int | None
    cost: float | None
    meta: dict[str, Any]
    scores: list[TraceScoreOut]


class TraceFilter(BaseModel):
    source: str | None = None
    failed: bool = False
    low_rated: bool = False
    long: bool = False
    new_topic: bool = False
    unused: bool = False
    prompt_version: str | None = None
    since: datetime | None = None
    until: datetime | None = None
    q: str | None = Field(default=None, max_length=200)


class MakeCases(BaseModel):
    trace_ids: list[uuid.UUID] | None = Field(default=None, max_length=1000)
    filter: TraceFilter | None = None
    variable: str = Field(default="input", min_length=1, max_length=64, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    max_cases: int = Field(default=100, ge=1, le=1000)
    dry_run: bool = False

    @model_validator(mode="after")
    def _something_chosen(self) -> "MakeCases":
        if not self.trace_ids and self.filter is None:
            raise ValueError("Choose some traces, or a filter, to make cases from.")
        return self


class MakeCasesOut(BaseModel):
    dataset_version_id: uuid.UUID | None
    considered: int
    created: int
    folded: int
    already_used: int
    empty: int
    dry_run: bool
    message: str


# ----------------------------------------------------------------------------------------------- settings


class ConfigOut(BaseModel):
    scrub_pii: bool
    scrub_emails: bool
    scrub_phones: bool
    scrub_cards: bool
    scrub_patterns: list[str]
    retention_days: int
    scoring_enabled: bool
    rule_sample_rate: float
    judge_sample_rate: float
    judge_monthly_limit: int


class ConfigUpdate(BaseModel):
    scrub_pii: bool | None = None
    scrub_emails: bool | None = None
    scrub_phones: bool | None = None
    scrub_cards: bool | None = None
    scrub_patterns: list[str] | None = Field(default=None, max_length=10)
    retention_days: int | None = Field(default=None, ge=1, le=365)
    scoring_enabled: bool | None = None
    rule_sample_rate: float | None = Field(default=None, ge=0, le=1)
    judge_sample_rate: float | None = Field(default=None, ge=0, le=1)
    judge_monthly_limit: int | None = Field(default=None, ge=0, le=1_000_000)

    @field_validator("scrub_patterns")
    @classmethod
    def _patterns_are_safe(cls, value: list[str] | None) -> list[str] | None:
        for pattern in value or []:
            problem = pattern_problem(pattern)
            if problem:
                raise ValueError(problem)
        return value


# ----------------------------------------------------------------------------------------------- tokens, stats


class TokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class TokenOut(BaseModel):
    id: uuid.UUID
    name: str
    prefix: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


class TokenCreated(TokenOut):
    token: str
    endpoint: str


class IngestDayOut(BaseModel):
    day: date
    accepted: int
    ignored: int
    dropped_rate: int
    dropped_size: int
    rejected_requests: int


class TrafficStats(BaseModel):
    total: int
    by_source: dict[str, int]
    by_state: dict[str, int]
    oldest: datetime | None
    newest: datetime | None
    retention_days: int
    days: list[IngestDayOut]
    dropped_recent: int
    judge_used_this_month: int
    judge_monthly_limit: int
    scoring_enabled: bool
    has_checks: bool
    email_available: bool


class DailyScore(BaseModel):
    day: date
    prompt_version: str | None
    traces: int
    errors: int
    scored: int
    passed: int
    pass_rate: float | None
    mean_quality: float | None
    judged: int


class ScoringRunOut(BaseModel):
    queued: bool
    message: str


class PurgeOut(BaseModel):
    deleted: int


# ----------------------------------------------------------------------------------------------- alerts


class ChannelCreate(BaseModel):
    kind: ChannelKind
    name: str = Field(min_length=1, max_length=200)
    target: str = Field(min_length=3, max_length=1000, description="The webhook or Slack address, or an email address.")

    @model_validator(mode="after")
    def _target_fits_kind(self) -> "ChannelCreate":
        target = self.target.strip()
        if self.kind is ChannelKind.EMAIL:
            if "@" not in target or " " in target:
                raise ValueError("Enter an email address such as team@example.com.")
        elif not target.lower().startswith(("http://", "https://")):
            raise ValueError("The address must start with http:// or https://.")
        self.target = target
        return self


class ChannelOut(BaseModel):
    id: uuid.UUID
    kind: ChannelKind
    name: str
    target_hint: str
    last_error: str | None
    last_sent_at: datetime | None


class ChannelTestOut(BaseModel):
    ok: bool
    message: str


class RuleBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    kind: AlertKind = AlertKind.DROP
    metric: AlertMetric = AlertMetric.PASS_RATE
    threshold: float = Field(default=0.8, gt=0, lt=1)
    margin: float = Field(default=0.1, gt=0, lt=0.5)
    window_days: int = Field(default=3, ge=1, le=30)
    baseline_days: int = Field(default=14, ge=3, le=90)
    min_samples: int = Field(default=30, ge=5, le=100_000)
    min_bad_days: int = Field(default=2, ge=1, le=30)
    channel_ids: list[uuid.UUID] = Field(default=[], max_length=10)
    quiet_start_hour: int | None = Field(default=None, ge=0, le=23)
    quiet_end_hour: int | None = Field(default=None, ge=0, le=23)
    quiet_utc_offset_min: int = Field(default=0, ge=-840, le=840)
    enabled: bool = True

    @model_validator(mode="after")
    def _consistent(self) -> "RuleBase":
        if self.min_bad_days > self.window_days:
            raise ValueError("The number of bad days can't be more than the days in the window.")
        if (self.quiet_start_hour is None) != (self.quiet_end_hour is None):
            raise ValueError("Set both the start and the end of the quiet hours, or neither.")
        return self


class RuleCreate(RuleBase):
    pass


class RuleOut(RuleBase):
    id: uuid.UUID
    created_at: datetime
    open_alert_id: uuid.UUID | None = None


class AlertOut(BaseModel):
    id: uuid.UUID
    rule_id: uuid.UUID
    rule_name: str
    status: AlertStatus
    title: str
    detail: dict[str, Any]
    created_at: datetime
    resolved_at: datetime | None
    notified_at: datetime | None
    notify_results: list[dict[str, Any]]


class EvaluateOut(BaseModel):
    opened: int
    resolved: int
    notified: int
