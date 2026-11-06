"""
The significance engine (DEVELOPMENT.md H4 step 4.5, decision 3): when is a difference between two sets of
results more than chance? Pure functions, no I/O.

The unit is the test case. Each model's answers to a case (several runs are averaged first) give one quality
number and one pass/fail (passed in more than half of its judged runs); only cases judged on both sides are
compared, and the number of cases left out is reported. The label comes from one rule: a paired bootstrap of
the mean difference in quality, resampling cases. *Clear difference* when the interval excludes zero, *no clear
difference* when it does not, *too few cases* below `MIN_CASES`. The pass-rate difference and an exact McNemar
test are reported as supporting detail and never decide the label. When one model is compared with several
others the interval is widened for the number of comparisons (Bonferroni). The seed comes from the compared
ids, so the same data always gives the same numbers, and swapping the two sides negates the interval and keeps
the label.
"""

import hashlib
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from statistics import NormalDist

import numpy as np

MIN_CASES = 10
RESAMPLES = 10_000
MIN_RESAMPLES = 1_000
ALPHA = 0.05
MAX_COMPARISONS = 50
WORK_BUDGET = 20_000_000  # resamples x cases drawn at most, so a huge run stays fast
CHUNK_ELEMENTS = 2_000_000  # memory bound for one block of draws
EXACT_LIMIT = 1_000  # above this many discordant cases McNemar uses the normal approximation

METHOD = (
    "Each test case is one data point (repeated runs are averaged). The difference in mean quality is resampled "
    "10,000 times over the cases; it is clear when the 95% interval of that difference excludes zero."
)


class Label(StrEnum):
    CLEAR = "clear difference"
    NONE = "no clear difference"
    TOO_FEW = "too few cases"


@dataclass(frozen=True)
class CaseResult:
    """One model's result on one test case: the mean quality of its judged runs and whether it mostly passed."""

    quality: float
    passed: bool


@dataclass(frozen=True)
class Comparison:
    label: Label
    cases: int  # cases judged on both sides: the ones compared
    only_first: int  # judged only on the first side
    only_second: int  # judged only on the second side
    mean_first: float | None
    mean_second: float | None
    difference: float | None  # first minus second
    low: float | None  # interval of the difference
    high: float | None
    level: float  # of the interval, after the multiple-comparison adjustment
    comparisons: int
    first_better: bool | None  # None when there is no clear difference
    pass_rate_first: float | None
    pass_rate_second: float | None
    first_only_passed: int  # cases only the first side passed
    second_only_passed: int
    mcnemar_p: float | None


def seed_for(*ids: object) -> int:
    """A seed that depends on which things are compared and not on their order."""
    digest = hashlib.sha256("\x1f".join(sorted(str(i) for i in ids)).encode()).digest()
    return int.from_bytes(digest[:8], "big")


def case_result(qualities: list[float], passes: list[bool]) -> CaseResult | None:
    """One case from its judged runs; None when no run was judged."""
    if not qualities:
        return None
    return CaseResult(quality=sum(qualities) / len(qualities), passed=sum(passes) * 2 > len(passes))


def mcnemar_exact(first_only: int, second_only: int) -> float:
    """Two-sided McNemar p-value from the discordant cases: exact binomial up to EXACT_LIMIT of them, then the
    normal approximation with continuity correction. No discordant case means no evidence: 1.0."""
    n = first_only + second_only
    if n == 0:
        return 1.0
    smaller = min(first_only, second_only)
    if n <= EXACT_LIMIT:
        tail = sum(math.comb(n, i) for i in range(smaller + 1))
        return float(min(1.0, 2.0 * tail / 2**n))
    z = (abs(first_only - second_only) - 1) / math.sqrt(n)
    return min(1.0, math.erfc(z / math.sqrt(2)))


def _resamples(cases: int) -> int:
    return max(MIN_RESAMPLES, min(RESAMPLES, WORK_BUDGET // max(cases, 1)))


def _expansion(n: int, alpha: float) -> float:
    """How much to widen the bootstrap interval for a small number of cases. A plain percentile interval is too
    narrow when n is small (it behaves as if the spread were known and divides by n, not n-1); widening it by
    t(n-1)/z x sqrt(n/(n-1)) makes it match the textbook t interval. The factor goes to 1 as n grows."""
    z = NormalDist().inv_cdf(1 - alpha / 2)
    df = n - 1
    t = (
        z
        + (z**3 + z) / (4 * df)
        + (5 * z**5 + 16 * z**3 + 3 * z) / (96 * df**2)
        + (3 * z**7 + 19 * z**5 + 17 * z**3 - 15 * z) / (384 * df**3)
    )
    return float(t / z * math.sqrt(n / df))


def bootstrap_interval(differences: list[float], alpha: float, seed: int) -> tuple[float, float]:
    """The percentile interval of the mean of `differences`, resampling the cases."""
    values = np.asarray(differences, dtype=float)
    n = len(values)
    count = _resamples(n)
    rng = np.random.default_rng(seed)
    means = np.empty(count)
    block = max(1, CHUNK_ELEMENTS // n)
    for start in range(0, count, block):
        size = min(block, count - start)
        means[start : start + size] = values[rng.integers(0, n, size=(size, n))].mean(axis=1)
    low, high = np.quantile(means, [alpha / 2, 1 - alpha / 2])
    centre, grow = float(values.mean()), _expansion(n, alpha)
    return centre - grow * (centre - float(low)), centre + grow * (float(high) - centre)


def compare(
    first: Mapping[str, CaseResult],
    second: Mapping[str, CaseResult],
    *,
    seed: int,
    comparisons: int = 1,
    alpha: float = ALPHA,
    min_cases: int = MIN_CASES,
) -> Comparison:
    """Compares two sets of per-case results (keyed by test case). `comparisons` is how many models the same
    model is being compared with, so the interval can be widened to keep the chance of a false "clear" low."""
    comparisons = min(max(comparisons, 1), MAX_COMPARISONS)
    adjusted = alpha / comparisons
    common = sorted(set(first) & set(second))
    n = len(common)
    a = [first[c] for c in common]
    b = [second[c] for c in common]
    first_only_passed = sum(x.passed and not y.passed for x, y in zip(a, b, strict=True))
    second_only_passed = sum(y.passed and not x.passed for x, y in zip(a, b, strict=True))
    mean_a = sum(r.quality for r in a) / n if n else None
    mean_b = sum(r.quality for r in b) / n if n else None
    low = high = None
    if n >= min_cases:
        low, high = bootstrap_interval([x.quality - y.quality for x, y in zip(a, b, strict=True)], adjusted, seed)
    clear = low is not None and high is not None and (low > 0 or high < 0)
    label = Label.CLEAR if clear else Label.NONE if n >= min_cases else Label.TOO_FEW
    return Comparison(
        label=label,
        cases=n,
        only_first=len(set(first) - set(second)),
        only_second=len(set(second) - set(first)),
        mean_first=mean_a,
        mean_second=mean_b,
        difference=None if mean_a is None or mean_b is None else mean_a - mean_b,
        low=low,
        high=high,
        level=1 - adjusted,
        comparisons=comparisons,
        first_better=(low is not None and low > 0) if clear else None,
        pass_rate_first=sum(r.passed for r in a) / n if n else None,
        pass_rate_second=sum(r.passed for r in b) / n if n else None,
        first_only_passed=first_only_passed,
        second_only_passed=second_only_passed,
        mcnemar_p=mcnemar_exact(first_only_passed, second_only_passed) if n else None,
    )


def compare_to_best(
    results: Mapping[str, Mapping[str, CaseResult]],
    best: str,
    *,
    seed_ids: Iterable[object] = (),
    min_cases: int = MIN_CASES,
) -> dict[str, Comparison]:
    """Every other model compared with `best` (first side = the other model), the interval widened for the
    number of models compared."""
    others = [m for m in results if m != best]
    return {
        m: compare(
            results[m],
            results[best],
            seed=seed_for(*seed_ids, m, best),
            comparisons=len(others),
            min_cases=min_cases,
        )
        for m in others
    }
