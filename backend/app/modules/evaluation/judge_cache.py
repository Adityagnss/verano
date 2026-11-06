"""
Judge result cache helpers (ADR 0021): the key a judged result is stored under, and a small bounded
least-recently-used layer in front of the database.

The key is a hash of everything the judge sees and everything that decides what it says: the check, its
criteria or steps and threshold, the judge model, and the case's inputs, expected answer, rubric, context and
the answer itself. Any change to any of them is a different key, so nothing stale is ever served. Pure code.
"""

import hashlib
import json
from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any


def cache_key(
    evaluator_name: str,
    config: dict[str, Any],
    threshold: float,
    judge_model: str,
    inputs: dict[str, Any],
    output: str,
    expected: str | None,
    rubric: Sequence[str] | None,
    context: Sequence[str],
    extras: dict[str, Any] | None = None,
) -> str:
    """A stable 64-character key for one judged check on one answer. `extras` is what else the judge was shown
    or how it was asked (the prompt, a reference, a combined call); with none, the key is what it always was."""
    parts: list[Any] = [evaluator_name, config, threshold, judge_model, inputs, output, expected, rubric, list(context)]
    if extras:
        parts.append(extras)
    payload = json.dumps(
        parts,
        sort_keys=True,
        default=str,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


@dataclass(frozen=True)
class CachedResult:
    value: float
    passed: bool
    reason: str


class RecentResults:
    """The most recently used results, at most `size` of them; the oldest is dropped first. O(1) per operation."""

    def __init__(self, size: int) -> None:
        self._size = max(size, 1)
        self._items: OrderedDict[str, CachedResult] = OrderedDict()

    def get(self, key: str) -> CachedResult | None:
        found = self._items.get(key)
        if found is not None:
            self._items.move_to_end(key)
        return found

    def put(self, key: str, result: CachedResult) -> None:
        self._items[key] = result
        self._items.move_to_end(key)
        while len(self._items) > self._size:
            self._items.popitem(last=False)

    def __len__(self) -> int:
        return len(self._items)
