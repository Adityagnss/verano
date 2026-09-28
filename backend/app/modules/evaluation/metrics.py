"""
Pure result metrics (DEVELOPMENT.md 4.2, base level: plain averages).

A case (one call) passes when every evaluator that applies to it passed; its quality is
the weighted mean of those evaluators' scores. A call that failed counts as a failed case
with quality 0. Per model: quality (mean case quality), pass rate, consistency (share of
test cases whose runs all got the same pass/fail result; only with 2+ runs), mean latency,
total cost and cost per call.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from statistics import mean

from app.modules.evaluation.domain import Score


@dataclass(frozen=True)
class WeightedScore:
    score: Score
    weight: float


@dataclass(frozen=True)
class CaseOutcome:
    model_profile_id: uuid.UUID
    model: str
    dataset_item_id: uuid.UUID
    run_number: int
    call_failed: bool
    passed: bool
    quality: float
    latency_ms: int | None
    cost: Decimal | None


@dataclass(frozen=True)
class ModelMetrics:
    model_profile_id: uuid.UUID
    model: str
    cases: int
    quality: float
    pass_rate: float
    consistency: float | None
    latency_ms: float | None
    cost: Decimal | None
    cost_per_call: Decimal | None
    failed_calls: int


def case_result(scores: list[WeightedScore]) -> tuple[bool, float]:
    if not scores:
        return True, 1.0
    total = sum(s.weight for s in scores) or 1.0
    quality = sum(s.score.value * s.weight for s in scores) / total
    return all(s.score.passed for s in scores), quality


def model_metrics(outcomes: list[CaseOutcome]) -> list[ModelMetrics]:
    by_model: dict[uuid.UUID, list[CaseOutcome]] = defaultdict(list)
    for outcome in outcomes:
        by_model[outcome.model_profile_id].append(outcome)
    return [_one(rows) for rows in by_model.values()]


def _one(rows: list[CaseOutcome]) -> ModelMetrics:
    by_item: dict[uuid.UUID, list[bool]] = defaultdict(list)
    for row in rows:
        by_item[row.dataset_item_id].append(row.passed)
    repeated = [results for results in by_item.values() if len(results) > 1]
    consistency = sum(len(set(r)) == 1 for r in repeated) / len(repeated) if repeated else None
    latencies = [r.latency_ms for r in rows if r.latency_ms is not None]
    costs = [r.cost for r in rows]
    cost = None if any(c is None for c in costs) else sum((c or Decimal(0) for c in costs), Decimal(0))
    return ModelMetrics(
        model_profile_id=rows[0].model_profile_id,
        model=rows[0].model,
        cases=len(rows),
        quality=mean(r.quality for r in rows),
        pass_rate=sum(r.passed for r in rows) / len(rows),
        consistency=consistency,
        latency_ms=mean(latencies) if latencies else None,
        cost=cost,
        cost_per_call=cost / len(rows) if cost is not None else None,
        failed_calls=sum(r.call_failed for r in rows),
    )
