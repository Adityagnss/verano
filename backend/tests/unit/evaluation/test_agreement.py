"""Labels and judge agreement (ADR 0017): the majority of people's labels, Cohen's kappa against a hand
calculation, Holm.
"""

import pytest

from app.modules.evaluation.agreement import agreement, holm_adjust, majority


def judged(table: list[tuple[bool, bool]]):  # type: ignore[no-untyped-def]
    return agreement(table, min_labels=20, raw_threshold=0.8, kappa_threshold=0.6)


def pairs(tp: int, fp: int, fn: int, tn: int) -> list[tuple[bool, bool]]:
    """(judge passed, people good) in the numbers of a 2x2 table."""
    return [(True, True)] * tp + [(True, False)] * fp + [(False, True)] * fn + [(False, False)] * tn


@pytest.mark.parametrize(
    ("labels", "verdict", "unsure"),
    [
        (["good", "good", "bad"], "good", 0),
        (["bad", "bad", "good", "unsure"], "bad", 1),
        (["good", "bad"], "disputed", 0),
        (["unsure", "unsure"], "unlabelled", 2),
        ([], "unlabelled", 0),
    ],
)
def test_the_majority_ignores_unsure_and_calls_a_tie_disputed(labels: list[str], verdict: str, unsure: int) -> None:
    found = majority(labels)
    assert (found.verdict, found.unsure) == (verdict, unsure)


def test_kappa_and_raw_agreement_equal_the_hand_calculation() -> None:
    # 8 true passes, 2 false passes, 2 false fails, 8 true fails: raw 16/20; chance 0.5; kappa (0.8 - 0.5) / 0.5
    stats = judged(pairs(8, 2, 2, 8))
    assert (stats.n, stats.agreed, stats.raw) == (20, 16, 0.8)
    assert stats.kappa == pytest.approx(0.6)
    assert (stats.tp, stats.fp, stats.fn, stats.tn) == (8, 2, 2, 8)
    assert not stats.warn
    assert not stats.too_few


def test_a_judge_that_agrees_no_better_than_chance_is_warned_about() -> None:
    stats = judged(pairs(5, 5, 5, 5))
    assert stats.raw == 0.5
    assert stats.kappa == pytest.approx(0.0)
    assert stats.warn


def test_too_few_labels_are_not_trusted_either_way() -> None:
    stats = judged(pairs(9, 0, 0, 10))
    assert stats.too_few
    assert not stats.warn
    assert stats.raw == 1.0


def test_kappa_is_undefined_when_everything_is_one_class() -> None:
    stats = judged(pairs(25, 0, 0, 0))
    assert stats.kappa is None
    assert stats.raw == 1.0
    assert judged([]).raw is None


def test_holm_adjusts_in_the_input_order_and_never_goes_down() -> None:
    assert holm_adjust([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])
    assert holm_adjust([0.6, 0.9]) == [1.0, 1.0]
    assert holm_adjust([]) == []
