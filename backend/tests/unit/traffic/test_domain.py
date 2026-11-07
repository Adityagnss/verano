"""Traffic's pure rules: scrubbing, caps, sampling, check combination, the drift test and quiet hours."""

import time
from datetime import UTC, date, datetime, timedelta

import pytest

from app.modules.traffic.domain import (
    CheckResult,
    DayPoint,
    ScrubConfig,
    bound_meta,
    clip,
    combine_checks,
    drift_verdict,
    fold_duplicates,
    in_quiet_hours,
    in_sample,
    judge_allowance,
    luhn_ok,
    pattern_problem,
    scrub_text,
    scrub_value,
    topic_hash,
)

TODAY = date(2026, 3, 20)
RULE = {
    "kind": "drop",
    "threshold": 0.8,
    "margin": 0.1,
    "window_days": 3,
    "baseline_days": 14,
    "min_samples": 30,
    "min_bad_days": 2,
}


def stream(good_rates: list[float], per_day: int = 100, end: date = TODAY) -> list[DayPoint]:
    """One DayPoint per day, oldest first, ending on `end`."""
    start = end - timedelta(days=len(good_rates) - 1)
    return [DayPoint(start + timedelta(days=i), round(rate * per_day), per_day) for i, rate in enumerate(good_rates)]


# ----------------------------------------------------------------------------------------------- scrubbing


def test_emails_phone_numbers_and_real_card_numbers_are_replaced_with_labels() -> None:
    text = "Mail ada@example.co.uk or call +44 20 7946 0958; card 4111 1111 1111 1111 thanks"
    cleaned, count = scrub_text(text, ScrubConfig())
    assert cleaned == "Mail [email] or call [phone]; card [card] thanks"
    assert count == 3


def test_a_number_that_fails_the_card_check_or_is_a_plain_date_or_order_number_is_kept() -> None:
    text = "Order 4471, shipped 2025-11-03, ref 4111 1111 1111 1112."
    cleaned, count = scrub_text(text, ScrubConfig())
    assert cleaned == text
    assert count == 0
    assert luhn_ok("4111111111111111")
    assert not luhn_ok("4111111111111112")


def test_the_owners_own_pattern_hides_matches_and_each_switch_turns_one_kind_off() -> None:
    config = ScrubConfig(patterns=(r"ACME-\d{6}",), emails=False)
    cleaned, count = scrub_text("id ACME-123456 mail a@b.io", config)
    assert cleaned == "id [hidden] mail a@b.io"
    assert count == 1
    assert scrub_text("a@b.io", ScrubConfig(enabled=False)) == ("a@b.io", 0)


@pytest.mark.parametrize("pattern", ["(a+)+$", "(.*a)*b", "", "x" * 201, "([unclosed"])
def test_a_pattern_that_could_run_forever_or_is_broken_is_refused(pattern: str) -> None:
    assert pattern_problem(pattern) is not None


def test_a_refused_pattern_in_a_stored_config_is_skipped_so_scrubbing_stays_fast() -> None:
    started = time.perf_counter()
    cleaned, _ = scrub_text("a" * 5_000 + "!", ScrubConfig(patterns=("(a+)+$",)))
    assert cleaned.startswith("aaa")
    assert time.perf_counter() - started < 1


def test_scrubbing_reaches_nested_metadata_text_and_leaves_keys_and_numbers() -> None:
    value = {"user": {"email": "x@y.com", "age": 41}, "notes": ["call +1 415 555 0100", 3]}
    cleaned, count = scrub_value(value, ScrubConfig())
    assert cleaned == {"user": {"email": "[email]", "age": 41}, "notes": ["call [phone]", 3]}
    assert count == 2


# ----------------------------------------------------------------------------------------------- caps


def test_clip_reports_a_cut_only_when_the_text_was_longer_than_the_cap() -> None:
    assert clip("abcdef", 6) == ("abcdef", False)
    assert clip("abcdefg", 6) == ("abcdef", True)


def test_metadata_is_bounded_in_keys_depth_text_and_total_size() -> None:
    many = {f"k{i}": "v" for i in range(60)}
    out, cut = bound_meta(many, 8_000)
    assert len(out) == 40
    assert cut
    deep, _ = bound_meta({"a": {"b": {"c": {"d": 1}}}}, 8_000)
    assert deep["a"]["b"]["c"] == "{'d': 1}"
    long, cut = bound_meta({"t": "x" * 900}, 8_000)
    assert len(long["t"]) == 500
    assert cut
    small, cut = bound_meta({"a": "x" * 400, "b": "y" * 400}, 500)
    assert cut
    assert len(str(small)) < 600
    assert len(small) == 1


# ----------------------------------------------------------------------------------------------- topics and folding


def test_questions_on_one_subject_share_a_topic_and_a_new_subject_gets_a_new_one() -> None:
    a = topic_hash("How do I reset my password for the account?")
    b = topic_hash("password reset account, how?")
    assert a == b != topic_hash("Where is my parcel shipping")


def test_near_duplicates_fold_into_the_first_and_known_vectors_absorb_repeats() -> None:
    x, y, z = [1.0, 0.0], [0.99, 0.141067], [0.0, 1.0]
    assert fold_duplicates([x, y, z], [], 0.95) == [-1, 0, -1]
    assert fold_duplicates([x, z], [[1.0, 0.0]], 0.95) == [-2, -1]


# ----------------------------------------------------------------------------------------------- sampling, checks


def test_sampling_is_stable_and_a_higher_rate_only_adds_traces() -> None:
    ids = [f"trace-{i}" for i in range(2_000)]
    five = {i for i in ids if in_sample(i, 0.05, "judge")}
    ten = {i for i in ids if in_sample(i, 0.10, "judge")}
    assert five == {i for i in ids if in_sample(i, 0.05, "judge")}
    assert five <= ten
    assert 60 <= len(five) <= 140
    assert 140 <= len(ten) <= 260
    assert all(in_sample(i, 1.0, "rule") for i in ids)
    assert not any(in_sample(i, 0.0, "rule") for i in ids)
    assert {i for i in ids if in_sample(i, 0.5, "rule")} != {i for i in ids if in_sample(i, 0.5, "judge")}


def test_a_trace_passes_when_every_required_check_passed_and_quality_is_the_weighted_mean() -> None:
    both = [CheckResult("a", 1.0, True, True, 1.0), CheckResult("b", 0.5, False, False, 3.0)]
    assert combine_checks(both) == (0.625, True)
    assert combine_checks([CheckResult("a", 0.0, False, True, 1.0)]) == (0.0, False)
    assert combine_checks([]) == (None, None)


def test_the_monthly_judge_limit_caps_how_many_more_may_be_judged() -> None:
    assert judge_allowance(500, 490, 50) == 10
    assert judge_allowance(500, 500, 5) == 0
    assert judge_allowance(500, 900, 5) == 0
    assert judge_allowance(500, 0, 5) == 5


# ----------------------------------------------------------------------------------------------- drift


def test_fourteen_good_days_then_a_sustained_drop_is_a_breach() -> None:
    points = stream([0.92] * 14 + [0.60, 0.58, 0.61])
    verdict = drift_verdict(points, today=TODAY, **RULE)
    assert verdict.breached
    assert verdict.bad_days == 3
    assert verdict.window_total == 300
    assert verdict.reference == pytest.approx(0.92)
    assert "below" in verdict.reason


def test_a_single_bad_day_never_alerts_however_bad_it_was() -> None:
    points = stream([0.92] * 16 + [0.10])
    verdict = drift_verdict(points, today=TODAY, **RULE)
    assert not verdict.breached
    assert verdict.bad_days == 1
    assert "fewer than the required number of days" in verdict.reason or verdict.llr is not None


def test_normal_noise_around_the_baseline_does_not_alert() -> None:
    points = stream(
        [0.92, 0.90, 0.93, 0.91, 0.92, 0.94, 0.90, 0.92, 0.91, 0.93, 0.92, 0.90, 0.92, 0.89, 0.91, 0.90, 0.93]
    )
    verdict = drift_verdict(points, today=TODAY, **RULE)
    assert not verdict.breached
    assert verdict.reason == "Within the expected range."


def test_a_window_with_too_few_traces_or_no_history_gives_no_verdict() -> None:
    few = stream([0.2] * 3, per_day=5)  # 15 traces in the window, below min_samples
    assert not drift_verdict(few, today=TODAY, **RULE).breached
    no_history = stream([0.2] * 3)
    verdict = drift_verdict(no_history, today=TODAY, **RULE)
    assert not verdict.breached
    assert "earlier traffic" in verdict.reason


def test_a_fixed_line_alerts_when_the_window_is_below_it_and_recovers_when_it_is_back() -> None:
    fixed = {**RULE, "kind": "threshold", "threshold": 0.85}
    bad = drift_verdict(stream([0.9] * 5 + [0.6, 0.6, 0.6]), today=TODAY, **fixed)
    assert bad.breached
    assert not bad.recovered
    back = drift_verdict(stream([0.9] * 5 + [0.6, 0.9, 0.9, 0.9], end=TODAY), today=TODAY, **fixed)
    assert back.recovered
    assert not back.breached


def test_recovery_needs_the_window_to_be_back_within_half_the_margin_of_the_line() -> None:
    assert drift_verdict(stream([0.92] * 14 + [0.92, 0.91, 0.89]), today=TODAY, **RULE).recovered
    still_low = drift_verdict(stream([0.92] * 14 + [0.92, 0.80, 0.80]), today=TODAY, **RULE)
    assert not still_low.recovered


# ----------------------------------------------------------------------------------------------- quiet hours


def at(hour: int) -> datetime:
    return datetime(2026, 3, 20, hour, 30, tzinfo=UTC)


def test_quiet_hours_wrap_past_midnight_and_follow_the_owners_utc_offset() -> None:
    assert in_quiet_hours(at(23), 22, 7, 0)
    assert in_quiet_hours(at(3), 22, 7, 0)
    assert not in_quiet_hours(at(12), 22, 7, 0)
    assert not in_quiet_hours(at(7), 22, 7, 0)
    assert in_quiet_hours(at(12), 22, 7, 600)  # 12:30 UTC is 22:30 at +10:00
    assert in_quiet_hours(at(9), 9, 17, 0)
    assert not in_quiet_hours(at(17), 9, 17, 0)


@pytest.mark.parametrize(("start", "end"), [(None, None), (5, None), (8, 8)])
def test_without_a_proper_window_there_are_no_quiet_hours(start: int | None, end: int | None) -> None:
    assert not in_quiet_hours(at(8), start, end, 0)
