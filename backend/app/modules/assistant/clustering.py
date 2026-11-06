"""
Embedding clustering of failures in bounded memory (ADR 0036). Pure code, no I/O.

Failures arrive as a stream, one embedding at a time, and are never all held at once. The clusterer keeps at most
`max_clusters` centroids (a running sum and a count) and a few example keys per cluster, so memory is
O(max_clusters x (dimensions + examples)) however many failures pass through, and time is O(failures x
max_clusters x dimensions).

For each vector: join the most similar cluster when it is similar enough; otherwise start a new one; when the
limit is reached, first merge the two closest clusters to make room. Vectors are assumed L2-normalized (the
embedders do that), so a dot product is the cosine similarity.
"""

import math
import random
from collections import Counter
from dataclasses import dataclass, field
from typing import Any


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=False))


def _unit(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


@dataclass
class ClusterState:
    total: list[float]
    count: int
    examples: list[tuple[str, Any]] = field(default_factory=list)
    seen: int = 0
    tags: dict[str, Counter[str]] = field(default_factory=dict)

    def centroid(self) -> list[float]:
        return _unit(self.total)


class OnlineClusterer:
    def __init__(self, max_clusters: int, similarity: float, examples: int, seed: int = 7) -> None:
        if max_clusters < 1:
            raise ValueError("At least one cluster is needed.")
        self.max_clusters = max_clusters
        self.similarity = similarity
        self.examples = examples
        self._random = random.Random(seed)
        self._clusters: list[ClusterState] = []
        self._centroids: list[list[float]] = []
        self.count = 0

    def add(self, key: str, vector: list[float], meta: dict[str, str] | None = None, payload: Any = None) -> None:
        self.count += 1
        best, best_similarity = self._nearest(vector)
        if best is not None and best_similarity >= self.similarity:
            self._join(best, (key, payload), vector, meta or {})
            return
        if len(self._clusters) >= self.max_clusters:
            self._merge_closest()
        self._clusters.append(ClusterState(total=[0.0] * len(vector), count=0))
        self._centroids.append(list(vector))
        self._join(len(self._clusters) - 1, (key, payload), vector, meta or {})

    def _nearest(self, vector: list[float]) -> tuple[int | None, float]:
        best: int | None = None
        best_similarity = -1.0
        for index, centroid in enumerate(self._centroids):
            similarity = _dot(vector, centroid)
            if similarity > best_similarity:
                best, best_similarity = index, similarity
        return best, best_similarity

    def _join(self, index: int, example: tuple[str, Any], vector: list[float], meta: dict[str, str]) -> None:
        cluster = self._clusters[index]
        cluster.total = [t + v for t, v in zip(cluster.total, vector, strict=False)]
        cluster.count += 1
        cluster.seen += 1
        self._centroids[index] = cluster.centroid()
        self._keep_example(cluster, example)
        for name, value in meta.items():
            cluster.tags.setdefault(name, Counter())[value] += 1

    def _keep_example(self, cluster: ClusterState, example: tuple[str, Any]) -> None:
        """Reservoir sampling: every member has the same chance of being one of the examples."""
        if len(cluster.examples) < self.examples:
            cluster.examples.append(example)
            return
        slot = self._random.randrange(cluster.seen)
        if slot < self.examples:
            cluster.examples[slot] = example

    def _merge_closest(self) -> None:
        best_pair = (0, 1)
        best_similarity = -2.0
        for i in range(len(self._centroids)):
            for j in range(i + 1, len(self._centroids)):
                similarity = _dot(self._centroids[i], self._centroids[j])
                if similarity > best_similarity:
                    best_pair, best_similarity = (i, j), similarity
        i, j = best_pair
        keep, drop = self._clusters[i], self._clusters[j]
        keep.total = [a + b for a, b in zip(keep.total, drop.total, strict=False)]
        keep.count += drop.count
        for example in drop.examples:
            keep.seen += 1
            self._keep_example(keep, example)
        keep.seen = keep.count
        for name, counter in drop.tags.items():
            keep.tags.setdefault(name, Counter()).update(counter)
        self._centroids[i] = keep.centroid()
        del self._clusters[j]
        del self._centroids[j]

    def clusters(self) -> list[ClusterState]:
        """Biggest first."""
        return sorted(self._clusters, key=lambda c: -c.count)
