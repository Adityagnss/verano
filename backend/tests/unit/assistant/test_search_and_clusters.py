"""Unit tests for Improve's search rules (Pareto fronts, sizing, labels) and the bounded failure clustering."""

import asyncio
import hashlib
import resource
import sys
import time
from collections.abc import AsyncIterator
from typing import Any

import pytest

from app.modules.assistant.clustering import OnlineClusterer
from app.modules.assistant.failures import MAX_FAILURES, analyse
from app.modules.assistant.search import (
    Point,
    cases_needed,
    dominates,
    fronts,
    pick_winner,
    quick_sample_size,
    round_label,
    spread_of,
)
from app.modules.generator.plugins.embedders import LexicalEmbedder

pytestmark = pytest.mark.unit


def test_pareto_fronts_and_winner() -> None:
    a = Point("a", 0.9, 5.0, 100)
    b = Point("b", 0.8, 1.0, 50)
    c = Point("c", 0.7, 6.0, 120)
    d = Point("d", 0.9, 5.0, 100)
    assert dominates(a, c) and not dominates(c, a) and not dominates(a, d) and not dominates(a, b)
    assert fronts([a, b, c]) == [["a", "b"], ["c"]]
    assert pick_winner([a, b, c]) == "a"
    assert pick_winner([a, d]) == "a"
    assert pick_winner([Point("x", 0.9, 9.0, 10), Point("y", 0.9, 2.0, 10)]) == "y"
    assert pick_winner([]) is None and fronts([]) == []


def test_sizing_and_labels() -> None:
    assert cases_needed(0.1, 0.25) == 50
    assert cases_needed(0.2, 0.25) < cases_needed(0.1, 0.25)
    with pytest.raises(ValueError, match="above zero"):
        cases_needed(0, 0.2)
    assert spread_of([0.5, 0.5]) == 0.05 and spread_of([1.0]) == 0.25
    assert quick_sample_size(100, 0.1, 0.25, low=8, high=20) == 8
    assert quick_sample_size(5, 0.1, 0.25, low=8, high=20) == 5
    assert quick_sample_size(100, 0.01, 0.25, low=8, high=20) == 20
    assert round_label(True, 30, 20) == "Proven on held-back cases"
    assert "only 5 held-back cases" in round_label(False, 5, 20)
    assert round_label(False, 30, 20) == "Not proven"


def blobs(count: int, groups: int) -> list[tuple[str, str]]:
    words = ["refund", "parcel", "crash", "password", "invoice", "delivery", "login", "warranty", "cancel", "upgrade"]
    topics = [" ".join(hashlib.md5(f"{g}-{k}".encode()).hexdigest()[:7] for k in range(8)) for g in range(groups)]
    return [(f"k{i}", f"{topics[i % groups]} {words[i % len(words)]}") for i in range(count)]


def test_clusterer_is_bounded_and_groups_similar_items() -> None:
    items = blobs(300, 5)
    clusterer = OnlineClusterer(max_clusters=8, similarity=0.6, examples=3)
    for (key, _), vector in zip(items, LexicalEmbedder().embed([t for _, t in items]), strict=True):
        clusterer.add(key, vector, {"tag": "t"}, payload=key)
    clusters = clusterer.clusters()
    assert len(clusters) <= 8 and sum(c.count for c in clusters) == 300
    assert [c.count for c in clusters] == sorted((c.count for c in clusters), reverse=True)
    assert all(len(c.examples) <= 3 for c in clusters)
    assert clusters[0].count >= 40
    with pytest.raises(ValueError, match="At least one"):
        OnlineClusterer(0, 0.6, 3)


def test_clusterer_merges_when_full() -> None:
    clusterer = OnlineClusterer(max_clusters=2, similarity=0.99, examples=2)
    for i, vector in enumerate([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [0.0, 0.0, 1.0]]):
        clusterer.add(f"k{i}", vector)
    assert len(clusterer.clusters()) == 2 and clusterer.count == 4
    assert sum(c.count for c in clusterer.clusters()) == 4


def failure_pages(total: int, batch: int) -> AsyncIterator[list[dict[str, Any]]]:
    async def pages() -> AsyncIterator[list[dict[str, Any]]]:
        rows = [
            {"run_id": f"r{i}", "tag": "wrong_label", "model": "m", "category": "c", "inputs": text, "output": text}
            | {"reasons": text}
            for i, (_, text) in enumerate(blobs(total, 12))
        ]
        for start in range(0, total, batch):
            yield rows[start : start + batch]

    return pages()


def test_a_thousand_failures_are_grouped_in_bounded_time_and_memory() -> None:
    unit = 1 if sys.platform == "darwin" else 1024  # ru_maxrss is bytes on macOS, kilobytes on Linux
    before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * unit
    started = time.perf_counter()
    result = asyncio.run(analyse(failure_pages(1000, 200), LexicalEmbedder(), 24, 0.6, 5))
    elapsed = time.perf_counter() - started
    growth_mb = (resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * unit - before) / (1024 * 1024)
    assert result.total == 1000 and result.clustered
    assert len(result.head) == MAX_FAILURES
    assert 1 < len(result.clusters) <= 24
    assert sum(c.size for c in result.clusters) == 1000
    assert all(len(c.examples) <= 5 for c in result.clusters)
    assert elapsed < 30
    assert growth_mb < 150


def test_a_small_run_is_not_clustered() -> None:
    result = asyncio.run(analyse(failure_pages(30, 10), LexicalEmbedder(), 24, 0.6, 5))
    assert result.total == 30 and not result.clustered and result.clusters == [] and len(result.head) == 30
