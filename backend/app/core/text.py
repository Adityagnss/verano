"""Small text helpers shared across modules."""

from typing import Any

CLIP_CHARS = 2_000


def clip(inputs: dict[str, Any], limit: int = CLIP_CHARS) -> dict[str, Any]:
    """An input file's text can be huge; prompts that only need a taste of a case get this."""
    return {key: value[:limit] if isinstance(value, str) else value for key, value in inputs.items()}


def bound(text: str, limit: int) -> tuple[str, bool]:
    """The text cut to `limit` characters and whether it was cut, so a stored answer can say it is incomplete."""
    return (text[:limit], True) if len(text) > limit else (text, False)
