"""
Pure result metrics (DEVELOPMENT.md 4.2, base level: plain averages).

A case (one call) passes when every evaluator that applies to it passed; its quality is
the weighted mean of those evaluators' scores. A call that failed counts as a failed case
with quality 0. A case is only *judged* when every evaluator that applies to it produced a
score: if any could not (the judge failed or is missing) the case is unscored, never a pass
and never a zero, and it is left out of quality, pass rate and consistency and counted
instead. Per model: quality (mean case quality over judged cases), pass rate, consistency
(share of test cases whose runs all got the same pass/fail result; only with 2+ runs), mean
latency, total cost and cost per call.
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
    scored: bool = True


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
    judged: bool = True


@dataclass(frozen=True)
class ModelMetrics:
    model_profile_id: uuid.UUID
    model: str
    cases: int
    judged_cases: int
    unscored_cases: int
    quality: float | None
    pass_rate: float | None
    consistency: float | None
    latency_ms: float | None
    cost: Decimal | None
    cost_per_call: Decimal | None
    failed_calls: int


def case_result(scores: list[WeightedScore]) -> tuple[bool, float, bool]:
    """(passed, quality, judged). A case with an unscored evaluator, or with no check that applied to it
    at all, is not judged: it has no result, and it never counts as a pass."""
    if not scores or any(not s.scored for s in scores):
        return False, 0.0, False
    total = sum(s.weight for s in scores) or 1.0
    quality = sum(s.score.value * s.weight for s in scores) / total
    return all(s.score.passed for s in scores), quality, True


def model_metrics(outcomes: list[CaseOutcome]) -> list[ModelMetrics]:
    by_model: dict[uuid.UUID, list[CaseOutcome]] = defaultdict(list)
    for outcome in outcomes:
        by_model[outcome.model_profile_id].append(outcome)
    return [_one(rows) for rows in by_model.values()]


def _one(rows: list[CaseOutcome]) -> ModelMetrics:
    judged = [r for r in rows if r.judged]
    by_item: dict[uuid.UUID, list[bool]] = defaultdict(list)
    for row in judged:
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
        judged_cases=len(judged),
        unscored_cases=len(rows) - len(judged),
        quality=mean(r.quality for r in judged) if judged else None,
        pass_rate=sum(r.passed for r in judged) / len(judged) if judged else None,
        consistency=consistency,
        latency_ms=mean(latencies) if latencies else None,
        cost=cost,
        cost_per_call=cost / len(rows) if cost is not None else None,
        failed_calls=sum(r.call_failed for r in rows),
    )
