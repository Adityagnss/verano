"""
Human labels and judge agreement (ADR 0017): pure functions, no I/O.

People label an answer good, bad or unsure. The majority of several people's labels gives one verdict per
answer: unsure labels are left out of the majority and counted separately, equal good and bad counts are
*disputed*, and an answer with no good or bad label is *unlabelled*. Agreement compares the judge's pass/fail
with the people's good/bad (positive = pass/good) on the answers that have a verdict: the raw share that
match, Cohen's kappa of the 2x2 table, and the four counts. Both numbers come from one pass over the pairs.
The thresholds and the minimum number of labels are given by the caller (they are settings, not constants
here). `holm_adjust` is the Holm-Bonferroni step-down adjustment of several p-values, in the input order.
"""

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Majority:
    verdict: str  # "good", "bad", "disputed" or "unlabelled"
    good: int
    bad: int
    unsure: int


@dataclass(frozen=True)
class AgreementStats:
    n: int  # answers used
    agreed: int
    raw: float | None  # share of answers where judge and people match; None when n == 0
    kappa: float | None  # Cohen's kappa; None when undefined (n == 0 or expected agreement == 1)
    tp: int  # judge passed, people good
    fp: int  # judge passed, people bad
    fn: int  # judge failed, people good
    tn: int  # judge failed, people bad
    too_few: bool
    warn: bool


def majority(labels: Sequence[str]) -> Majority:
    """The people's verdict on one answer from its labels ("good", "bad" or "unsure")."""
    good = bad = unsure = 0
    for label in labels:
        if label == "good":
            good += 1
        elif label == "bad":
            bad += 1
        else:
            unsure += 1
    if good > bad:
        verdict = "good"
    elif bad > good:
        verdict = "bad"
    elif good:
        verdict = "disputed"
    else:
        verdict = "unlabelled"
    return Majority(verdict=verdict, good=good, bad=bad, unsure=unsure)


def agreement(
    pairs: Sequence[tuple[bool, bool]], *, min_labels: int, raw_threshold: float, kappa_threshold: float
) -> AgreementStats:
    """Agreement of the judge with the people from (judge_passed, people_good) pairs, in one pass."""
    tp = fp = fn = tn = 0
    for judge_passed, people_good in pairs:
        if judge_passed:
            if people_good:
                tp += 1
            else:
                fp += 1
        elif people_good:
            fn += 1
        else:
            tn += 1
    n = tp + fp + fn + tn
    agreed = tp + tn
    raw = agreed / n if n else None
    kappa = None
    if n:
        expected = (tp + fp) * (tp + fn) + (fn + tn) * (fp + tn)  # times 1/n^2
        if expected != n * n:
            kappa = (agreed * n - expected) / (n * n - expected)
    too_few = n < min_labels
    warn = not too_few and (
        (raw is not None and raw < raw_threshold) or (kappa is not None and kappa < kappa_threshold)
    )
    return AgreementStats(
        n=n, agreed=agreed, raw=raw, kappa=kappa, tp=tp, fp=fp, fn=fn, tn=tn, too_few=too_few, warn=warn
    )


def holm_adjust(p_values: Sequence[float]) -> list[float]:
    """Holm-Bonferroni adjusted p-values in the input order, each capped at 1.0."""
    m = len(p_values)
    order = sorted(range(m), key=p_values.__getitem__)
    adjusted = [0.0] * m
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, min(1.0, (m - rank) * p_values[index]))
        adjusted[index] = running
    return adjusted
