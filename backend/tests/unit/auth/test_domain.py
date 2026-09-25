"""Unit tests for refresh-token judgement: rotation, reuse detection, revocation, expiry."""

from datetime import UTC, datetime, timedelta

import pytest

from app.modules.auth.domain import RefreshOutcome, RefreshTokenState, judge_refresh

pytestmark = [pytest.mark.unit, pytest.mark.auth]

NOW = datetime(2026, 9, 25, tzinfo=UTC)
LATER = NOW + timedelta(days=1)


@pytest.mark.parametrize(
    ("state", "outcome"),
    [
        (RefreshTokenState(expires_at=LATER, used_at=None, revoked_at=None), RefreshOutcome.ROTATE),
        (RefreshTokenState(expires_at=LATER, used_at=NOW, revoked_at=None), RefreshOutcome.REUSED),
        (RefreshTokenState(expires_at=LATER, used_at=NOW, revoked_at=NOW), RefreshOutcome.REVOKED),
        (RefreshTokenState(expires_at=NOW, used_at=None, revoked_at=None), RefreshOutcome.EXPIRED),
    ],
)
def test_presented_refresh_token_is_judged_from_its_stored_state(
    state: RefreshTokenState, outcome: RefreshOutcome
) -> None:
    assert judge_refresh(state, NOW) is outcome
