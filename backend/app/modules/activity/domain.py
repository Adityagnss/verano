"""
Pure Activity logic (no I/O): the two periods compared, their UTC bounds, the model name shown
and the identity of a key.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass(frozen=True)
class Periods:
    start: date  # first day of the period shown
    end: date  # last day, today in the viewer's time zone
    prior_start: date  # the period before, of the same length, ends the day before `start`

    def utc_bounds(self, zone: ZoneInfo) -> tuple[datetime, datetime]:
        """From the start of the prior period to the end of today, as UTC instants."""
        first = datetime.combine(self.prior_start, time.min, zone).astimezone(UTC)
        after = datetime.combine(self.end + timedelta(days=1), time.min, zone).astimezone(UTC)
        return first, after


def zone_of(name: str) -> ZoneInfo | None:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return None


def periods(today: date, days: int) -> Periods:
    start = today - timedelta(days=days - 1)
    return Periods(start=start, end=today, prior_start=start - timedelta(days=days))


def model_name(stored: str) -> str:
    """Calls store the LiteLLM name `<prefix>/<model>`; people know the model by the rest."""
    return stored.split("/", 1)[1] if "/" in stored else stored


def key_id(provider: str, last4: str | None) -> str:
    return f"{provider}:{last4}" if last4 else f"{provider}:no key"
