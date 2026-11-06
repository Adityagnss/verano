"""
Apps schemas: the user's own app as a test target (ADR 0024), what a "send one test case" shows, and the
shape of one call's result.

A target names an address, a request template (JSON with the case's inputs filled in), and where to find the
answer, the retrieved chunks, the tool calls and the cost in the app's reply (a small JSONPath subset, never
code). Secrets (a bearer token, a basic-auth password, secret headers) are accepted once and never returned.
"""

import uuid
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, SecretStr, field_validator


class AuthKind(StrEnum):
    NONE = "none"
    BEARER = "bearer"
    BASIC = "basic"
    HEADERS = "headers"


class AppMode(StrEnum):
    SINGLE = "single"
    CONVERSATION = "conversation"


class AppTargetBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=1, max_length=1000)
    method: str = Field(default="POST", pattern="^(GET|POST|PUT|PATCH)$")
    mode: AppMode = AppMode.SINGLE
    request_template: str = Field(min_length=1, max_length=20_000)
    answer_path: str = Field(min_length=1, max_length=500)
    chunks_path: str | None = Field(default=None, max_length=500)
    tool_calls_path: str | None = Field(default=None, max_length=500)
    cost_path: str | None = Field(default=None, max_length=500)
    timeout_s: float | None = Field(default=None, gt=0, le=600)
    concurrency: int | None = Field(default=None, ge=1, le=64)
    retries: int | None = Field(default=None, ge=0, le=5)

    @field_validator("url")
    @classmethod
    def _http_url(cls, value: str) -> str:
        if not value.lower().startswith(("http://", "https://")):
            raise ValueError("The address must start with http:// or https://.")
        return value.strip()


class AppTargetCreate(AppTargetBase):
    auth_kind: AuthKind = AuthKind.NONE
    bearer_token: SecretStr | None = None
    basic_username: str | None = None
    basic_password: SecretStr | None = None
    headers: dict[str, SecretStr] = {}


class AppTargetUpdate(BaseModel):
    """Every field optional. Secrets are left as they are unless new ones are sent."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    url: str | None = Field(default=None, max_length=1000)
    method: str | None = Field(default=None, pattern="^(GET|POST|PUT|PATCH)$")
    mode: AppMode | None = None
    request_template: str | None = Field(default=None, min_length=1, max_length=20_000)
    answer_path: str | None = Field(default=None, min_length=1, max_length=500)
    chunks_path: str | None = None
    tool_calls_path: str | None = None
    cost_path: str | None = None
    timeout_s: float | None = Field(default=None, gt=0, le=600)
    concurrency: int | None = Field(default=None, ge=1, le=64)
    retries: int | None = Field(default=None, ge=0, le=5)
    auth_kind: AuthKind | None = None
    bearer_token: SecretStr | None = None
    basic_username: str | None = None
    basic_password: SecretStr | None = None
    headers: dict[str, SecretStr] | None = None


class AppTargetOut(BaseModel):
    id: uuid.UUID
    credential_id: uuid.UUID
    model_profile_id: uuid.UUID
    name: str
    url: str
    method: str
    mode: AppMode
    request_template: str
    answer_path: str
    chunks_path: str | None
    tool_calls_path: str | None
    cost_path: str | None
    auth_kind: AuthKind
    header_names: list[str]
    timeout_s: float
    concurrency: int
    retries: int


class AppTestRequest(BaseModel):
    inputs: dict[str, Any]


class AppReplyOut(BaseModel):
    answer: str
    chunks: list[str]
    tool_calls: list[dict[str, Any]]
    cost: float | None


class AppTestOut(BaseModel):
    """Exactly what was sent and what came back, and what Verano could read from it."""

    request_body: str
    status_code: int | None
    response_body: str | None
    truncated: bool
    latency_ms: int | None
    reply: AppReplyOut | None
    error: str | None
