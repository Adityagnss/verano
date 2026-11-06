"""
Feature switches (decision E2): a built feature can be switched off by name with `VERANO_DISABLED_FEATURES`.

Everything that has passed its tests is on by default. A switched-off feature refuses its routes with a message
that says how to turn it on, and its entry points are hidden; nothing else changes.
"""

from collections.abc import Awaitable, Callable

from fastapi import Depends

from app.core.config import Settings, get_settings
from app.core.errors import Conflict

APPS = "apps"
CODE_CHECKS = "code_checks"
SWITCHED_OFF = (
    "This feature ({name}) is switched off on this server. Remove it from VERANO_DISABLED_FEATURES to use it."
)


def is_enabled(settings: Settings, name: str) -> bool:
    return name not in settings.disabled_features


def require_feature(name: str) -> Callable[..., Awaitable[None]]:
    """A route dependency that refuses the request while the feature is switched off."""

    async def check(settings: Settings = Depends(get_settings)) -> None:
        if not is_enabled(settings, name):
            raise Conflict(SWITCHED_OFF.format(name=name))

    return check
