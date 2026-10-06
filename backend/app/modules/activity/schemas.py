"""Activity page schemas: the workspace's model usage per day, for this period and the one before."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.modules.gateway.schemas import CallPurpose


class ActivityQuery(BaseModel):
    days: int = Field(30, ge=1, le=365)
    tz: str = Field("UTC", max_length=64)


class ActivityRow(BaseModel):
    """One day's calls for one project, key, model and purpose."""

    period: Literal["current", "prior"]
    day: date
    project_id: uuid.UUID
    key: str | None  # provider + last four characters; one real key used in many projects is one key
    provider: str
    model: str
    purpose: CallPurpose
    requests: int
    failed: int
    input_tokens: int
    output_tokens: int
    # Only calls whose provider reported the detail count here (older calls and many providers don't)
    cached_input_tokens: int
    reasoning_tokens: int
    input_tokens_with_cache_report: int
    cost: Decimal
    unknown_price_calls: int


class ActivityProject(BaseModel):
    id: uuid.UUID
    name: str


class ActivityKey(BaseModel):
    id: str
    provider: str
    last4: str | None
    labels: list[str]
    projects: int


class FailureCount(BaseModel):
    error_type: str
    count: int


class ActivityOut(BaseModel):
    timezone: str
    days: int
    start: date
    end: date
    prior_start: date
    rows: list[ActivityRow]
    projects: list[ActivityProject]
    keys: list[ActivityKey]
    failures: list[FailureCount]
