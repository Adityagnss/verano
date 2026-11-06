"""
Glue between results and the significance engine: per-case results from scored outcomes, the comparison of every
model with the best one, and the API shape of a comparison. Pure apart from a small in-process cache.
"""

import uuid
from collections import OrderedDict, defaultdict
from collections.abc import Iterable, Sequence

from app.modules.evaluation.metrics import CaseOutcome, ModelMetrics
from app.modules.evaluation.schemas import ComparisonOut
from app.modules.evaluation.significance import METHOD, MIN_CASES, CaseResult, Comparison, case_result, compare_to_best

CACHE_SIZE = 256
_cache: "OrderedDict[tuple[object, ...], dict[uuid.UUID, ComparisonOut]]" = OrderedDict()


def case_results(outcomes: Iterable[CaseOutcome]) -> dict[str, CaseResult]:
    """One result per test case from the judged runs among `outcomes` (cases with no judged run are left out)."""
    grouped: dict[str, list[CaseOutcome]] = defaultdict(list)
    for outcome in outcomes:
        if outcome.judged:
            grouped[str(outcome.dataset_item_id)].append(outcome)
    results = (
        (item, case_result([o.quality for o in rows], [o.passed for o in rows])) for item, rows in grouped.items()
    )
    return {item: found for item, found in results if found is not None}


def comparison_out(found: Comparison) -> ComparisonOut:
    first, second = found.pass_rate_first, found.pass_rate_second
    return ComparisonOut(
        label=found.label,
        cases=found.cases,
        only_first=found.only_first,
        only_second=found.only_second,
        difference=found.difference,
        low=found.low,
        high=found.high,
        level=found.level,
        comparisons=found.comparisons,
        first_better=found.first_better,
        pass_rate_difference=first - second if first is not None and second is not None else None,
        first_only_passed=found.first_only_passed,
        second_only_passed=found.second_only_passed,
        mcnemar_p=found.mcnemar_p,
        method=METHOD,
    )


def best_by_quality(metrics: Sequence[ModelMetrics]) -> ModelMetrics | None:
    judged = [m for m in metrics if m.quality is not None]
    return max(judged, key=lambda m: (m.quality or 0.0, m.model), default=None)


def versus_best(
    run_id: uuid.UUID,
    experiment_id: uuid.UUID,
    metrics: Sequence[ModelMetrics],
    outcomes: Sequence[CaseOutcome],
    min_cases: int = MIN_CASES,
) -> dict[uuid.UUID, ComparisonOut]:
    """For every judged model except the best on quality: how it compares with the best. A finished scoring pass
    never changes, so the answer is kept (bounded) instead of resampled on every read."""
    key = (run_id, min_cases)
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]
    best = best_by_quality(metrics)
    found: dict[uuid.UUID, ComparisonOut] = {}
    if best is not None:
        per_model: dict[str, dict[str, CaseResult]] = {}
        for m in metrics:
            if m.quality is not None:
                per_model[str(m.model_profile_id)] = case_results(
                    o for o in outcomes if o.model_profile_id == m.model_profile_id
                )
        if len(per_model) > 1:
            compared = compare_to_best(
                per_model, str(best.model_profile_id), seed_ids=[experiment_id], min_cases=min_cases
            )
            found = {uuid.UUID(model): comparison_out(c) for model, c in compared.items()}
    _cache[key] = found
    while len(_cache) > CACHE_SIZE:
        _cache.popitem(last=False)
    return found
