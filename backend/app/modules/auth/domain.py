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

from app.core.permissions import Role, outranks


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


class InviteStatus(StrEnum):
    OPEN = "open"
    ACCEPTED = "accepted"
    EXPIRED = "expired"
    REVOKED = "revoked"


def invite_status(
    expires_at: datetime, accepted_at: datetime | None, revoked_at: datetime | None, now: datetime
) -> InviteStatus:
    if accepted_at is not None:
        return InviteStatus.ACCEPTED
    if revoked_at is not None:
        return InviteStatus.REVOKED
    if expires_at <= now:
        return InviteStatus.EXPIRED
    return InviteStatus.OPEN


def role_change_problem(actor: Role, current: Role | None, new: Role | None, owners_left: int) -> str | None:
    """Why this change of someone's role (or removal, `new` None) is not allowed, in plain words; None when it is.
    `owners_left` is how many owners the workspace would still have afterwards."""
    if new is not None and not outranks(actor, new):
        return f"Your role can't give the {new.value} role. Ask an owner."
    if current is not None and not outranks(actor, current):
        return f"Your role can't change someone who is {current.value}. Ask an owner."
    if current is Role.OWNER and (new is not Role.OWNER) and owners_left < 1:
        return "A workspace needs at least one owner. Make someone else an owner first."
    return None


def email_domain(email: str) -> str:
    return email.rsplit("@", 1)[-1].lower()


def normalize_email(email: str) -> str:
    return email.strip().lower()


def password_problem(password: str, min_length: int) -> str | None:
    if len(password) < min_length:
        return f"Use at least {min_length} characters for your password."
    return None
