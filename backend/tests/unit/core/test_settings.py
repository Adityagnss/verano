"""Unit tests for the production guard on development-only settings."""

from typing import Any

import pytest
from pydantic import ValidationError

from app.core.config import Settings

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"refresh_cookie_secure": False}, "VERANO_REFRESH_COOKIE_SECURE must be true"),
        ({"mock_provider_enabled": True}, "VERANO_MOCK_PROVIDER_ENABLED must be false"),
    ],
)
def test_production_refuses_development_only_settings(overrides: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        Settings(_env_file=None, environment="production", **overrides)


def test_development_allows_a_non_secure_cookie_for_local_http() -> None:
    assert Settings(_env_file=None, refresh_cookie_secure=False).refresh_cookie_secure is False
