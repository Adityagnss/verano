"""
Traffic tables (ADR 0031, ADR 0032).

`traffic_traces` holds what real users asked and what the app answered: imported from a file or received live,
cleaned of personal data and cut to size before it is stored. `traffic_scores` holds each check's result for a sampled
trace; `traffic_configs` the project's choices (scrubbing, retention, sampling, judge limit); `traffic_tokens` the
tokens an app sends spans with; `traffic_ingest_days` how much came in and how much was dropped each day;
`traffic_alert_channels`, `traffic_alert_rules` and `traffic_alerts` the alerting. Every table is scoped by project and
deleted with it.
"""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, ForeignKey, Index, LargeBinary, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, CreatedAtMixin, IdMixin


class TrafficConfig(Base):
    __tablename__ = "traffic_configs"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True)
    scrub_pii: Mapped[bool]
    scrub_emails: Mapped[bool]
    scrub_phones: Mapped[bool]
    scrub_cards: Mapped[bool]
    scrub_patterns: Mapped[list[Any]]
    retention_days: Mapped[int]
    scoring_enabled: Mapped[bool]
    rule_sample_rate: Mapped[float]
    judge_sample_rate: Mapped[float]
    judge_monthly_limit: Mapped[int]


class TrafficToken(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "traffic_tokens"
    __table_args__ = (Index(None, "project_id", "id"), Index(None, "token_hash", unique=True))

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    token_hash: Mapped[str] = mapped_column(String(64))
    prefix: Mapped[str] = mapped_column(String(16))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    last_used_at: Mapped[datetime | None]
    revoked_at: Mapped[datetime | None]


class TrafficTrace(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "traffic_traces"
    __table_args__ = (
        Index(None, "project_id", "id"),
        Index(None, "project_id", "started_at"),
        Index(None, "project_id", "topic_hash", "started_at"),
        Index(None, "project_id", "source", "external_id", unique=True),
        Index(None, "project_id", "score_state", "id"),
        Index(None, "project_id", "created_at"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    source: Mapped[str] = mapped_column(String(16))
    external_id: Mapped[str | None] = mapped_column(String(200))
    started_at: Mapped[datetime]
    input_text: Mapped[str] = mapped_column(Text)
    output_text: Mapped[str] = mapped_column(Text)
    input_truncated: Mapped[bool] = mapped_column(default=False, server_default="false")
    output_truncated: Mapped[bool] = mapped_column(default=False, server_default="false")
    status: Mapped[str] = mapped_column(String(8))
    error_message: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[int | None]
    model: Mapped[str | None] = mapped_column(String(200))
    prompt_version: Mapped[str | None] = mapped_column(String(100))
    rating: Mapped[float | None]
    tokens_in: Mapped[int | None]
    tokens_out: Mapped[int | None]
    cost: Mapped[float | None]
    meta: Mapped[dict[str, Any]]
    scrubbed_count: Mapped[int] = mapped_column(default=0, server_default="0")
    topic_hash: Mapped[str] = mapped_column(String(12))
    case_made_at: Mapped[datetime | None]
    score_state: Mapped[str] = mapped_column(String(16), default="new", server_default="new")
    judge_sampled: Mapped[bool] = mapped_column(default=False, server_default="false")
    judged: Mapped[bool] = mapped_column(default=False, server_default="false")
    judged_at: Mapped[datetime | None]
    scored_at: Mapped[datetime | None]
    quality: Mapped[float | None]
    passed: Mapped[bool | None]


class TrafficScore(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "traffic_scores"
    __table_args__ = (Index(None, "trace_id"),)

    trace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("traffic_traces.id", ondelete="CASCADE"))
    evaluator_name: Mapped[str] = mapped_column(String(100))
    value: Mapped[float]
    passed: Mapped[bool]
    judged: Mapped[bool]
    required: Mapped[bool]
    weight: Mapped[float]
    reason: Mapped[str] = mapped_column(Text)


class TrafficIngestDay(Base):
    __tablename__ = "traffic_ingest_days"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    accepted: Mapped[int] = mapped_column(default=0, server_default="0")
    ignored: Mapped[int] = mapped_column(default=0, server_default="0")
    dropped_rate: Mapped[int] = mapped_column(default=0, server_default="0")
    dropped_size: Mapped[int] = mapped_column(default=0, server_default="0")
    rejected_requests: Mapped[int] = mapped_column(default=0, server_default="0")


class AlertChannel(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "traffic_alert_channels"
    __table_args__ = (Index(None, "project_id", "id"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(200))
    target_secret: Mapped[bytes] = mapped_column(LargeBinary)
    target_hint: Mapped[str] = mapped_column(String(300))
    last_error: Mapped[str | None] = mapped_column(Text)
    last_sent_at: Mapped[datetime | None]


class AlertRule(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "traffic_alert_rules"
    __table_args__ = (Index(None, "project_id", "id"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(16))
    metric: Mapped[str] = mapped_column(String(16))
    threshold: Mapped[float]
    margin: Mapped[float]
    window_days: Mapped[int]
    baseline_days: Mapped[int]
    min_samples: Mapped[int]
    min_bad_days: Mapped[int]
    channel_ids: Mapped[list[Any]]
    quiet_start_hour: Mapped[int | None]
    quiet_end_hour: Mapped[int | None]
    quiet_utc_offset_min: Mapped[int] = mapped_column(default=0, server_default="0")
    enabled: Mapped[bool] = mapped_column(default=True, server_default="true")


class Alert(IdMixin, CreatedAtMixin, Base):
    """One incident. A rule has at most one open incident at a time (a partial unique index), so a problem that lasts
    for days raises one alert, not one per check."""

    __tablename__ = "traffic_alerts"
    __table_args__ = (
        Index(None, "project_id", "id"),
        Index(None, "rule_id", unique=True, postgresql_where=text("status = 'open'")),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    rule_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("traffic_alert_rules.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(300))
    detail: Mapped[dict[str, Any]]
    resolved_at: Mapped[datetime | None]
    notified_at: Mapped[datetime | None]
    notify_results: Mapped[list[Any]]
