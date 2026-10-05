"""
The llm_calls table: one row per logical gateway call, whatever its purpose.

A row records the exact parameters sent (after filtering), the request messages, the
output, tokens, cost (NULL when the model's price is unknown, never 0), latency of the
successful attempt, the number of attempts and the final error if it failed. It is the
basis of cost tracking for test runs, generation, judge and assistant calls alike.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, CreatedAtMixin, IdMixin, str_enum
from app.modules.gateway.schemas import CallPurpose, CallStatus


class LLMCall(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "llm_calls"
    __table_args__ = (
        Index(None, "project_id", "id"),
        Index(None, "project_id", "purpose"),
        Index(None, "experiment_id"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    credential_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("provider_credentials.id", ondelete="SET NULL"))
    experiment_id: Mapped[uuid.UUID | None]
    test_case_run_id: Mapped[uuid.UUID | None]
    purpose: Mapped[CallPurpose] = mapped_column(str_enum(CallPurpose, "call_purpose"))
    status: Mapped[CallStatus] = mapped_column(str_enum(CallStatus, "call_status"))
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(400))
    response_model: Mapped[str | None] = mapped_column(String(400))
    params: Mapped[dict[str, Any]]
    request_messages: Mapped[list[Any]]
    output_text: Mapped[str | None] = mapped_column(Text)
    finish_reason: Mapped[str | None] = mapped_column(String(64))
    input_tokens: Mapped[int | None]
    output_tokens: Mapped[int | None]
    cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    latency_ms: Mapped[int | None]
    ttft_ms: Mapped[int | None]
    attempts: Mapped[int]
    error_type: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    labels: Mapped[dict[str, Any]]
    trace_id: Mapped[str] = mapped_column(String(32))
    span_id: Mapped[str] = mapped_column(String(16))
    started_at: Mapped[datetime]
    completed_at: Mapped[datetime]
