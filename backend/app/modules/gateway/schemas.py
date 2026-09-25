"""
Gateway contract and schemas.

`Message`, `CallPurpose`, `CallContext` and `LLMResult` form the gateway contract
(DEVELOPMENT.md 1.1): every module that needs a model calls
`GatewayService.complete(model_id, messages, params, credential_id, purpose, context)`
and gets an `LLMResult`, or `complete_json(..., schema)` and gets a validated model.
The mock provider's configuration schemas live here too, because the gateway is where
the mock is installed into LiteLLM.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class CallPurpose(StrEnum):
    TEST_RUN = "test_run"
    GENERATION = "generation"
    JUDGE = "judge"
    ASSISTANT = "assistant"


class CallStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class CallContext(BaseModel):
    project_id: uuid.UUID
    experiment_id: uuid.UUID | None = None
    test_case_run_id: uuid.UUID | None = None
    trace_id: str | None = None
    parent_span_id: str | None = None
    labels: dict[str, str] = {}


class LLMResult(BaseModel):
    call_id: uuid.UUID
    text: str
    finish_reason: str | None
    input_tokens: int
    output_tokens: int
    cost: Decimal | None
    latency_ms: int
    attempts: int
    model: str
    provider: str
    params: dict[str, Any]
    trace_id: str
    span_id: str


class ProviderResponse(BaseModel):
    text: str
    finish_reason: str | None
    input_tokens: int
    output_tokens: int
    headers: dict[str, str] = {}


class TestCallRequest(BaseModel):
    __test__ = False

    credential_id: uuid.UUID
    model: str
    messages: list[Message] = Field(min_length=1)
    params: dict[str, Any] = {}


class LLMCallOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    purpose: CallPurpose
    status: CallStatus
    provider: str
    model: str
    params: dict[str, Any]
    input_tokens: int | None
    output_tokens: int | None
    cost: Decimal | None
    latency_ms: int | None
    attempts: int
    error_type: str | None
    error_message: str | None
    created_at: datetime


class PurposeCost(BaseModel):
    calls: int
    cost: Decimal
    calls_with_unknown_price: int


class CostSummary(BaseModel):
    calls: int
    cost: Decimal
    calls_with_unknown_price: int
    by_purpose: dict[CallPurpose, PurposeCost]


class MockModelSpec(BaseModel):
    behavior: str
    display_name: str | None = None
    input_price_per_mtok: Decimal
    output_price_per_mtok: Decimal
    context_window: int = 8192
    max_output_tokens: int = 2048
    latency_ms: int = 0
    accuracy: float | None = None
    failure_rate: float = 0.0
    failure_mix: dict[str, float] = {}
    fail_first: list[str] = []
    inner: str | None = None
    retry_after_s: float = 1.0
    supported_parameters: list[str] = ["temperature", "top_p", "max_tokens", "seed", "stop", "response_format"]
    response_headers: dict[str, str] = {}


class MockModelsConfig(BaseModel):
    seed: int
    models: dict[str, MockModelSpec]


class MockScript(BaseModel):
    match: str
    response: str


class MockScriptFile(BaseModel):
    responses: list[MockScript]


class MockAnswerKey(BaseModel):
    answers: dict[str, str]
