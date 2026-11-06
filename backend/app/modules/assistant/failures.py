"""
Streaming failure analysis (ADR 0036): reads the failed answers of a scored run a page at a time and never holds
them all.

`failure_pages` yields failures in batches straight from the database (keyed pages of calls, their scores, their test
cases), so memory is one batch however large the run is. `FailureAnalysis` consumes the batches: the first
`MAX_FAILURES` are kept as they are (a small run is grouped by one model call, as before); when there are more, it
embeds failures batch by batch and feeds an online clusterer with a fixed number of clusters, so a 1,000-failure run
costs a bounded amount of memory and time and the model is asked only to *name* the biggest clusters.
"""

import asyncio
import uuid
from collections import Counter
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.text import clip
from app.modules.assistant.clustering import OnlineClusterer
from app.modules.assistant.domain import rule_tag
from app.modules.datasets.schemas import Split
from app.modules.datasets.service import DatasetService
from app.modules.engine.models import Experiment, TestCaseRun
from app.modules.engine.schemas import RunStatus
from app.modules.evaluation.domain import Score as ScoreValue
from app.modules.evaluation.domain import inputs_text
from app.modules.evaluation.metrics import WeightedScore, case_result
from app.modules.evaluation.models import Score
from app.modules.generator.plugins.embedders import Embedder

MAX_FAILURES = 40
CALL_ERROR = "call_error"


def failure_text(failure: dict[str, Any]) -> str:
    """What is embedded for one failure: its kind, the input, the answer and why it failed."""
    return " ".join(str(failure.get(key) or "")[:300] for key in ("tag", "inputs", "output", "reasons"))


async def failure_pages(
    session: AsyncSession, datasets: DatasetService, experiment: Experiment, run_id: uuid.UUID, split: Split, batch: int
) -> AsyncIterator[list[dict[str, Any]]]:
    after: uuid.UUID | None = None
    while True:
        query = select(TestCaseRun).where(
            TestCaseRun.experiment_id == experiment.id,
            TestCaseRun.status.in_([RunStatus.SUCCEEDED, RunStatus.FAILED]),
        )
        if after is not None:
            query = query.where(TestCaseRun.id > after)
        rows = list((await session.scalars(query.order_by(TestCaseRun.id).limit(batch))).all())
        if not rows:
            return
        after = rows[-1].id
        scores: dict[uuid.UUID, list[Score]] = {}
        found = await session.scalars(
            select(Score).where(
                Score.experiment_id == experiment.id,
                Score.evaluation_run_id == run_id,
                Score.test_case_run_id.in_([r.id for r in rows]),
            )
        )
        for score in found.all():
            scores.setdefault(score.test_case_run_id, []).append(score)
        items = {
            i.id: i for i in await datasets.items(experiment.dataset_version_id, ids=[r.dataset_item_id for r in rows])
        }
        failures = []
        for row in rows:
            item = items.get(row.dataset_item_id)
            if item is None or item.split is not split:
                continue
            own = scores.get(row.id, [])
            weighted = [
                WeightedScore(ScoreValue(s.value, s.passed, s.reason), s.weight, scored=s.status != "unscored")
                for s in own
            ]
            passed, _, _ = case_result(weighted)
            if passed and row.status is RunStatus.SUCCEEDED:
                continue
            failed = {s.evaluator_name for s in own if not s.passed}
            if row.status is RunStatus.FAILED:
                failed.add(CALL_ERROR)
            failures.append(
                {
                    "run_id": str(row.id),
                    "tag": rule_tag(row.raw_output, failed),
                    "model": row.model,
                    "category": item.category,
                    "inputs": clip(item.inputs)
                    if set(item.inputs) != {"attachment"}
                    else inputs_text(clip(item.inputs)),
                    "expected": item.expected_output,
                    "output": row.raw_output or row.error_message,
                    "reasons": "; ".join(s.reason for s in own if not s.passed),
                }
            )
        if failures:
            yield failures


@dataclass
class ClusterSummary:
    size: int
    examples: list[dict[str, Any]]
    tags: Counter[str]
    models: Counter[str]
    categories: Counter[str]


@dataclass
class FailureAnalysis:
    total: int = 0
    head: list[dict[str, Any]] = field(default_factory=list)
    clusters: list[ClusterSummary] = field(default_factory=list)

    @property
    def clustered(self) -> bool:
        return self.total > MAX_FAILURES


async def analyse(
    pages: AsyncIterator[list[dict[str, Any]]], embedder: Embedder, max_clusters: int, similarity: float, examples: int
) -> FailureAnalysis:
    result = FailureAnalysis()
    clusterer: OnlineClusterer | None = None

    async def feed(clusterer_: OnlineClusterer, batch: list[dict[str, Any]]) -> None:
        vectors = await asyncio.to_thread(embedder.embed, [failure_text(f) for f in batch])
        for failure, vector in zip(batch, vectors, strict=True):
            clusterer_.add(
                failure["run_id"],
                vector,
                {"tag": failure["tag"], "model": failure["model"], "category": failure["category"]},
                failure,
            )

    async for batch in pages:
        before = len(result.head)
        for failure in batch:
            result.total += 1
            if len(result.head) < MAX_FAILURES:
                result.head.append(failure)
        taken = len(result.head) - before  # the part of this batch that went into the head
        if clusterer is not None:
            await feed(clusterer, batch)
        elif result.total > MAX_FAILURES:
            clusterer = OnlineClusterer(max_clusters, similarity, examples)
            await feed(clusterer, result.head)
            await feed(clusterer, batch[taken:])
    if clusterer is not None:
        result.clusters = [
            ClusterSummary(
                size=c.count,
                examples=[payload for _, payload in c.examples],
                tags=c.tags.get("tag", Counter()),
                models=c.tags.get("model", Counter()),
                categories=c.tags.get("category", Counter()),
            )
            for c in clusterer.clusters()
        ]
    return result
