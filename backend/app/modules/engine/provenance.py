"""
Which model version the provider says answered (DEVELOPMENT.md H2 step 4).

A model name can be an alias: the provider decides which snapshot sits behind it and may
change it. Every call records the id the provider reported. A model *changed* when its calls
came back under more than one id, within one experiment or between two experiments with the
same configuration. Calls with no reported id are counted but never make a change: nothing
is known about them.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass


@dataclass(frozen=True)
class ReturnedModel:
    id: str | None
    calls: int


def summarize(rows: list[tuple[uuid.UUID, str | None, int]]) -> dict[uuid.UUID, list[ReturnedModel]]:
    """Per model: the ids reported and how many calls each answered, most calls first."""
    grouped: dict[uuid.UUID, list[ReturnedModel]] = defaultdict(list)
    for model_id, reported, calls in rows:
        grouped[model_id].append(ReturnedModel(reported, calls))
    return {model_id: sorted(found, key=lambda r: (-r.calls, r.id or "")) for model_id, found in grouped.items()}


def known(versions: list[ReturnedModel]) -> set[str]:
    return {r.id for r in versions if r.id}


def changed_within(versions: list[ReturnedModel]) -> bool:
    return len(known(versions)) > 1


def changed_between(before: list[ReturnedModel], after: list[ReturnedModel]) -> bool:
    """Both sides reported ids and the sets differ."""
    old, new = known(before), known(after)
    return bool(old) and bool(new) and old != new
