"""
Pure audit rules: the CSV and JSON export forms and the cleaning of details before they are stored.

Details never hold secrets: any value stored under a key that looks like a secret is replaced, so a caller that
passes a request body by mistake cannot put a key into the log. CSV cells that start with a character a
spreadsheet would run as a formula are prefixed with an apostrophe.
"""

import csv
import io
from collections.abc import Iterable
from typing import Any

from app.modules.audit.schemas import AuditEventOut

SECRET_WORDS = ("key", "secret", "token", "password", "authorization")
SAFE_KEYS = frozenset({"key_last4", "key_name", "key_label", "token_name", "token_prefix"})
REDACTED = "(hidden)"
FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")
CSV_COLUMNS = ("when", "who", "what", "summary", "project_id", "target_type", "target_id", "details")


def clean_details(details: dict[str, Any] | None) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for name, value in (details or {}).items():
        safe = name in SAFE_KEYS or name.endswith("_id")
        looks_secret = not safe and any(word in name.lower() for word in SECRET_WORDS)
        if looks_secret:
            cleaned[name] = REDACTED
        elif isinstance(value, dict):
            cleaned[name] = clean_details(value)
        else:
            cleaned[name] = value
    return cleaned


def _cell(value: object) -> str:
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(FORMULA_STARTS) else text


def to_csv(events: Iterable[AuditEventOut]) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(CSV_COLUMNS)
    for event in events:
        writer.writerow(
            [
                _cell(event.created_at.isoformat()),
                _cell(event.actor_name or "Unknown"),
                _cell(event.action_label),
                _cell(event.summary),
                _cell(event.project_id),
                _cell(event.target_type),
                _cell(event.target_id),
                _cell(event.details if event.details else ""),
            ]
        )
    return out.getvalue()
