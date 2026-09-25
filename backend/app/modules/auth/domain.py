"""
Pure auth rules: email normalization, password policy and refresh-token judgement.

`judge_refresh` decides what presenting a refresh token means, given only its stored
state and the current time. A token that was already rotated (`used_at` set) being shown
again is the signature of theft, so the outcome is REUSED and the caller revokes the whole
family. No I/O here; the service applies the outcome.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class RefreshOutcome(StrEnum):
    ROTATE = "rotate"
    REUSED = "reused"
    REVOKED = "revoked"
    EXPIRED = "expired"


@dataclass(frozen=True)
class RefreshTokenState:
    expires_at: datetime
    used_at: datetime | None
    revoked_at: datetime | None


def judge_refresh(state: RefreshTokenState, now: datetime) -> RefreshOutcome:
    if state.revoked_at is not None:
        return RefreshOutcome.REVOKED
    if state.used_at is not None:
        return RefreshOutcome.REUSED
    if state.expires_at <= now:
        return RefreshOutcome.EXPIRED
    return RefreshOutcome.ROTATE


def normalize_email(email: str) -> str:
    return email.strip().lower()


def password_problem(password: str, min_length: int) -> str | None:
    if len(password) < min_length:
        return f"Use at least {min_length} characters for your password."
    return None
