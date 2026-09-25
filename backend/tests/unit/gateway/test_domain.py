"""Unit tests for the gateway's pure rules: parameters, cost, retries, adaptive limits, JSON."""

from decimal import Decimal

import pytest

from app.core.errors import InvalidParameter, ProviderAuthError, ProviderTimeout, RateLimited
from app.modules.gateway.domain import (
    AdaptiveLimit,
    AdaptivePolicy,
    after_success,
    after_throttle,
    backoff_delay,
    compute_cost,
    extract_json,
    filter_params,
    parse_rate_headers,
    should_retry,
    start_limit,
)
from app.modules.registry.schemas import ParameterRange, RateLimitHeaders

pytestmark = [pytest.mark.unit, pytest.mark.gateway]

ALLOWED = {"temperature": ParameterRange(min=0.0, max=1.0), "max_tokens": ParameterRange(min=1, max=4096)}
POLICY = AdaptivePolicy(decrease_factor=0.5, increase_fraction=0.1, floor_fraction=0.05)


def test_unsupported_params_are_removed_and_reported() -> None:
    result = filter_params({"temperature": 0.2, "top_p": 0.9, "logit_bias": {}, "max_tokens": 50}, ALLOWED)
    assert result.sent == {"temperature": 0.2, "max_tokens": 50}
    assert result.dropped == ["logit_bias", "top_p"]


def test_out_of_range_param_is_rejected_never_clamped() -> None:
    with pytest.raises(InvalidParameter) as error:
        filter_params({"temperature": 1.5}, ALLOWED)
    assert error.value.details["values"] == {"temperature": 1.5}


def test_cost_uses_per_million_token_prices_exactly() -> None:
    assert compute_cost(1_000, 500, Decimal("0.15"), Decimal("0.60")) == Decimal("0.00045")


@pytest.mark.parametrize(("input_price", "output_price"), [(None, Decimal(1)), (Decimal(1), None), (None, None)])
def test_unknown_price_gives_no_cost_never_zero(input_price: Decimal | None, output_price: Decimal | None) -> None:
    assert compute_cost(1_000, 500, input_price, output_price) is None


def test_only_transient_errors_are_retried_and_only_while_attempts_remain() -> None:
    assert should_retry(RateLimited("x"), attempt=1, max_attempts=3)
    assert should_retry(ProviderTimeout("x"), attempt=2, max_attempts=3)
    assert not should_retry(ProviderTimeout("x"), attempt=3, max_attempts=3)
    assert not should_retry(ProviderAuthError("x"), attempt=1, max_attempts=3)


def test_backoff_honours_retry_after_and_otherwise_grows_exponentially_with_jitter() -> None:
    assert backoff_delay(1, retry_after_s=7.0, base_s=0.5, cap_s=30, jitter=0.0) == 7.0
    delays = [backoff_delay(attempt, None, base_s=0.5, cap_s=30, jitter=1.0) for attempt in (1, 2, 3)]
    assert delays == [0.5, 1.0, 2.0]
    assert backoff_delay(3, None, base_s=0.5, cap_s=30, jitter=0.0) == 1.0
    assert backoff_delay(20, None, base_s=0.5, cap_s=30, jitter=1.0) == 30


def test_a_429_halves_the_rate_and_successes_recover_it_gradually() -> None:
    state = start_limit(default=100, override=None)
    throttled = after_throttle(state, POLICY)
    assert throttled.current == 50
    recovered = after_success(throttled, default=100, override=None, reported_limit=None, policy=POLICY)
    assert recovered.current == 60
    assert after_throttle(AdaptiveLimit(ceiling=100, current=5), POLICY).current == 5


def test_ceiling_prefers_user_override_then_provider_headers_then_catalog_default() -> None:
    fresh = start_limit(default=60, override=None)
    learned = after_success(fresh, default=60, override=None, reported_limit=5000, policy=POLICY)
    assert (learned.ceiling, learned.current) == (5000, 5000)
    overridden = after_success(learned, default=60, override=200, reported_limit=5000, policy=POLICY)
    assert overridden.ceiling == 200
    assert overridden.current <= 200


def test_rate_headers_are_read_case_insensitively_from_the_first_matching_name() -> None:
    names = RateLimitHeaders(limit_requests=["x-ratelimit-limit-requests"], retry_after=["retry-after"])
    parsed = parse_rate_headers({"X-RateLimit-Limit-Requests": "3000", "Retry-After": "12"}, names)
    assert (parsed.limit_requests, parsed.retry_after_s) == (3000, 12.0)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('{"a": 1}', '{"a": 1}'),
        ('```json\n{"a": 1}\n```', '{"a": 1}'),
        ('Sure! Here it is: {"a": {"b": [1]}} Hope that helps.', '{"a": {"b": [1]}}'),
        ("Result:\n```\n[1, 2]\n```", "[1, 2]"),
        ('{"answer": ', '{"answer":'),
    ],
)
def test_json_is_extracted_from_fences_and_surrounding_prose(raw: str, expected: str) -> None:
    assert extract_json(raw).strip() == expected
