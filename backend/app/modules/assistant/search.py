"""
The search half of Improve (ADR 0036): pure functions, no I/O.

- `fronts` sorts candidates into Pareto fronts by non-domination on quality (higher is better), cost and prompt
  length (lower is better). Front 0 is every candidate no other candidate beats on all three at once.
- `pick_winner` takes front 0 and chooses the highest quality there (ties: cheaper, then shorter, then id).
- `cases_needed` is the number of cases needed to see a difference of a given size with a given spread, for the
  normal-approximation paired test (80% power, 5% two-sided by default).
- `quick_sample_size` turns that into the small sample used by the quick check.
- `round_label` says in plain words what a finished round proved.
"""

import math
from dataclasses import dataclass
from statistics import NormalDist, pstdev


@dataclass(frozen=True)
class Point:
    key: str
    quality: float
    cost: float
    length: int


def dominates(a: Point, b: Point) -> bool:
    """`a` is at least as good as `b` on all three measures and strictly better on one."""
    at_least = a.quality >= b.quality and a.cost <= b.cost and a.length <= b.length
    strictly = a.quality > b.quality or a.cost < b.cost or a.length < b.length
    return at_least and strictly


def fronts(points: list[Point]) -> list[list[str]]:
    """Non-dominated sorting: front 0, then what is left after removing it, and so on. Keys, in input order."""
    remaining = list(points)
    result: list[list[str]] = []
    while remaining:
        front = [p for p in remaining if not any(dominates(other, p) for other in remaining if other is not p)]
        result.append([p.key for p in front])
        taken = {p.key for p in front}
        remaining = [p for p in remaining if p.key not in taken]
    return result


def pick_winner(points: list[Point]) -> str | None:
    if not points:
        return None
    first = set(fronts(points)[0])
    chosen = min((p for p in points if p.key in first), key=lambda p: (-p.quality, p.cost, p.length, p.key))
    return chosen.key


def cases_needed(effect: float, spread: float, alpha: float = 0.05, power: float = 0.8) -> int:
    """Paired-difference sample size: n = ((z(1-alpha/2) + z(power)) * spread / effect) ** 2, rounded up.
    `effect` is the quality difference worth detecting; `spread` is the standard deviation of the per-case
    difference (the per-case quality spread is a safe stand-in)."""
    if effect <= 0:
        raise ValueError("The difference to detect must be above zero.")
    normal = NormalDist()
    z = normal.inv_cdf(1 - alpha / 2) + normal.inv_cdf(power)
    return max(2, math.ceil((z * max(spread, 1e-6) / effect) ** 2))


def spread_of(qualities: list[float]) -> float:
    """Spread of per-case quality, floored so an all-equal sample does not ask for 2 cases."""
    return max(pstdev(qualities), 0.05) if len(qualities) > 1 else 0.25


def quick_sample_size(available: int, effect: float, spread: float, low: int, high: int) -> int:
    """The quick check looks for a big difference only (two and a half times the target), so a small sample is
    enough to drop the clearly weak candidates; the full test and the held-back test decide the rest."""
    wanted = cases_needed(effect * 2.5, spread)
    return min(available, max(low, min(high, wanted)))


def round_label(proven: bool, cases: int, minimum: int) -> str:
    if proven:
        return "Proven on held-back cases"
    if cases < minimum:
        return f"Not proven: only {cases} held-back cases (at least {minimum} needed)"
    return "Not proven"
