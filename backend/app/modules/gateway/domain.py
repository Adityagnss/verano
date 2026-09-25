"""
Pure gateway logic: parameter filtering, cost, retry timing, adaptive rate limits and JSON
extraction.

- `filter_params` keeps only parameters the model profile accepts and rejects values
  outside a declared range; it never silently changes a value, because the exact
  parameters sent are part of an experiment's record.
- `compute_cost` returns None when either price is unknown, so an unknown price can never
  turn into a $0 cost.
- Rate limits are adaptive (AIMD): the ceiling is the per-credential override, else the
  limit the provider reports in its headers, else the catalog default; a 429 cuts the
  current rate multiplicatively, and each success grows it back by a fraction of the
  ceiling.
- `PendingCall` carries one logical call through its attempts and builds its record.
No I/O; the service and plugins apply these decisions.
"""

import json
import re
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from typing import Any

from app.core.errors import AppError, InvalidParameter
from app.modules.gateway.schemas import CallContext, CallPurpose, Message
from app.modules.registry.schemas import CallTarget, ModelProfileOut, ParameterRange, RateLimitHeaders

PER_MILLION = Decimal(1_000_000)
FENCE = re.compile(r"```(?:json|JSON)?\s*(.*?)```", re.DOTALL)
OPENERS = {"{": "}", "[": "]"}


@dataclass(frozen=True)
class FilteredParams:
    sent: dict[str, Any]
    dropped: list[str]


def allowed_parameters(profile: ModelProfileOut, json_mode_parameter: str) -> dict[str, ParameterRange]:
    allowed = dict(profile.parameters)
    if profile.supports_json_mode:
        allowed[json_mode_parameter] = ParameterRange()
    return allowed


def _out_of_range(value: Any, bounds: ParameterRange) -> bool:
    if bounds.min is None and bounds.max is None:
        return False
    if isinstance(value, bool) or not isinstance(value, int | float):
        return True
    return (bounds.min is not None and value < bounds.min) or (bounds.max is not None and value > bounds.max)


def filter_params(params: dict[str, Any], allowed: dict[str, ParameterRange]) -> FilteredParams:
    sent = {name: value for name, value in params.items() if name in allowed and value is not None}
    invalid = {name: value for name, value in sent.items() if _out_of_range(value, allowed[name])}
    if invalid:
        ranges = {name: allowed[name].model_dump() for name in invalid}
        raise InvalidParameter(
            "Some parameter values are outside what this model accepts.", {"values": invalid, "ranges": ranges}
        )
    return FilteredParams(sent=sent, dropped=sorted(set(params) - set(sent)))


def compute_cost(
    input_tokens: int, output_tokens: int, input_price_per_mtok: Decimal | None, output_price_per_mtok: Decimal | None
) -> Decimal | None:
    if input_price_per_mtok is None or output_price_per_mtok is None:
        return None
    return (Decimal(input_tokens) * input_price_per_mtok + Decimal(output_tokens) * output_price_per_mtok) / PER_MILLION


def estimate_tokens(messages: list[Message], max_output: int | None, chars_per_token: int) -> int:
    prompt_chars = sum(len(message.content) for message in messages)
    return prompt_chars // chars_per_token + 1 + (max_output or 0)


def should_retry(error: AppError, attempt: int, max_attempts: int) -> bool:
    return error.retryable and attempt < max_attempts


def backoff_delay(attempt: int, retry_after_s: float | None, base_s: float, cap_s: float, jitter: float) -> float:
    if retry_after_s is not None:
        return min(retry_after_s + jitter * base_s, cap_s)
    ceiling = min(cap_s, base_s * 2.0 ** (attempt - 1))
    return ceiling / 2 + jitter * ceiling / 2


@dataclass(frozen=True)
class RateHeaders:
    limit_requests: int | None = None
    remaining_requests: int | None = None
    limit_tokens: int | None = None
    remaining_tokens: int | None = None
    retry_after_s: float | None = None


def _first_number(headers: dict[str, str], names: list[str]) -> float | None:
    lowered = {key.lower(): value for key, value in headers.items()}
    for name in names:
        try:
            return float(lowered[name.lower()])
        except (KeyError, ValueError):
            continue
    return None


def _as_int(value: float | None) -> int | None:
    return int(value) if value is not None else None


def parse_rate_headers(headers: dict[str, str], names: RateLimitHeaders) -> RateHeaders:
    return RateHeaders(
        limit_requests=_as_int(_first_number(headers, names.limit_requests)),
        remaining_requests=_as_int(_first_number(headers, names.remaining_requests)),
        limit_tokens=_as_int(_first_number(headers, names.limit_tokens)),
        remaining_tokens=_as_int(_first_number(headers, names.remaining_tokens)),
        retry_after_s=_first_number(headers, names.retry_after),
    )


@dataclass(frozen=True)
class AdaptiveLimit:
    ceiling: float
    current: float
    learned: float | None = None


@dataclass(frozen=True)
class AdaptivePolicy:
    decrease_factor: float
    increase_fraction: float
    floor_fraction: float


def resolve_ceiling(default: int, override: int | None, learned: float | None) -> float:
    if override is not None:
        return float(override)
    return float(learned) if learned is not None else float(default)


def start_limit(default: int, override: int | None) -> AdaptiveLimit:
    ceiling = resolve_ceiling(default, override, None)
    return AdaptiveLimit(ceiling=ceiling, current=ceiling)


def after_success(
    state: AdaptiveLimit, default: int, override: int | None, reported_limit: int | None, policy: AdaptivePolicy
) -> AdaptiveLimit:
    learned = float(reported_limit) if reported_limit else state.learned
    ceiling = resolve_ceiling(default, override, learned)
    current = min(ceiling, state.current + policy.increase_fraction * ceiling)
    if reported_limit and state.learned is None and override is None:
        current = ceiling
    return AdaptiveLimit(ceiling=ceiling, current=current, learned=learned)


def after_throttle(state: AdaptiveLimit, policy: AdaptivePolicy) -> AdaptiveLimit:
    floor = max(state.ceiling * policy.floor_fraction, 1.0)
    return replace(state, current=max(floor, state.current * policy.decrease_factor))


def extract_json(raw: str) -> str:
    fenced = FENCE.search(raw)
    text = fenced.group(1) if fenced else raw
    starts = [index for index in (text.find(opener) for opener in OPENERS) if index >= 0]
    if not starts:
        return text.strip()
    start = min(starts)
    end = text.rfind(OPENERS[text[start]])
    return text[start : end + 1] if end > start else text[start:]


def parse_json(raw: str) -> Any:
    return json.loads(extract_json(raw))


def with_instruction(messages: list[Message], instruction: str, system_supported: bool) -> list[Message]:
    if system_supported:
        systems = [m for m in messages if m.role == "system"]
        rest = [m for m in messages if m.role != "system"]
        merged = "\n\n".join([*(m.content for m in systems), instruction])
        return [Message(role="system", content=merged), *rest]
    first_user = next(i for i, m in enumerate(messages) if m.role == "user")
    updated = Message(role="user", content=f"{messages[first_user].content}\n\n{instruction}")
    return [*messages[:first_user], updated, *messages[first_user + 1 :]]


@dataclass
class PendingCall:
    target: CallTarget
    messages: list[Message]
    filtered: FilteredParams
    purpose: CallPurpose
    context: CallContext
    started_at: datetime
    trace_id: str
    span_id: str
    estimated_tokens: int
    attempts: int = 0

    def record(self, completed_at: datetime) -> dict[str, Any]:
        dropped = {"dropped_params": ",".join(self.filtered.dropped)} if self.filtered.dropped else {}
        return {
            "project_id": self.context.project_id,
            "credential_id": self.target.credential_id,
            "experiment_id": self.context.experiment_id,
            "test_case_run_id": self.context.test_case_run_id,
            "purpose": self.purpose,
            "provider": self.target.provider,
            "model": self.target.profile.litellm_model,
            "params": self.filtered.sent,
            "request_messages": [message.model_dump() for message in self.messages],
            "attempts": self.attempts,
            "labels": {**self.context.labels, **dropped},
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "started_at": self.started_at,
            "completed_at": completed_at,
        }
