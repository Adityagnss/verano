"""The Activity page's periods, their UTC bounds in a time zone, and model and key names."""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from app.modules.activity.domain import key_id, model_name, periods, zone_of


def test_a_period_ends_today_and_the_prior_one_has_the_same_length() -> None:
    span = periods(date(2026, 10, 6), 30)
    assert (span.start, span.end, span.prior_start) == (date(2026, 9, 7), date(2026, 10, 6), date(2026, 8, 8))
    one_day = periods(date(2026, 10, 6), 1)
    assert (one_day.start, one_day.prior_start) == (date(2026, 10, 6), date(2026, 10, 5))


def test_days_are_whole_days_in_the_viewer_s_time_zone() -> None:
    first, after = periods(date(2026, 10, 6), 1).utc_bounds(ZoneInfo("Asia/Kolkata"))
    assert first == datetime(2026, 10, 4, 18, 30, tzinfo=UTC)
    assert after == datetime(2026, 10, 6, 18, 30, tzinfo=UTC)


def test_names_people_know() -> None:
    assert model_name("openrouter/nvidia/nemotron-3-super-120b-a12b:free") == "nvidia/nemotron-3-super-120b-a12b:free"
    assert model_name("ollama_chat/qwen2.5:3b") == "qwen2.5:3b"
    assert key_id("openrouter", "245a") == "openrouter:245a"
    assert key_id("ollama", None) == "ollama:no key"
    assert zone_of("Asia/Kolkata") is not None
    assert zone_of("Mars/Olympus") is None
