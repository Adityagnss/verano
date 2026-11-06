"""Pure rules for the workspace spending limit: the month window and when a limit counts as reached."""

from datetime import UTC, datetime
from decimal import Decimal

LIMIT_REACHED = (
    "Your workspace's monthly spending limit of ${limit} was reached (${spent} spent since {since}). "
    "An owner or admin can raise it in Settings, Guardrails."
)


def month_start(now: datetime) -> datetime:
    """The first moment of the current calendar month, in UTC."""
    utc = now.astimezone(UTC)
    return utc.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def limit_reached(spent: Decimal, limit: Decimal | None) -> bool:
    return limit is not None and spent >= limit


def percent_used(spent: Decimal, limit: Decimal | None) -> float | None:
    if limit is None or limit <= 0:
        return None
    return round(float(spent / limit) * 100, 1)


def reached_message(spent: Decimal, limit: Decimal, now: datetime) -> str:
    return LIMIT_REACHED.format(limit=f"{limit:.2f}", spent=f"{spent:.2f}", since=month_start(now).strftime("%b %d"))
