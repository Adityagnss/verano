"""
Unit tests for the significance engine: hand-computed answers for the exact test and for simple data, the
labels and their edge cases, determinism and symmetry, bounded work on huge runs, and a calibration test
(simulated comparisons with no true difference must rarely say "clear"; a real difference must be found).
"""

import time
from collections.abc import Mapping

import numpy as np
import pytest

from app.modules.evaluation import significance as sig
from app.modules.evaluation.significance import CaseResult, Label, case_result, compare, mcnemar_exact, seed_for


def results(qualities: list[float], passed: list[bool] | None = None, prefix: str = "c") -> dict[str, CaseResult]:
    flags = passed if passed is not None else [q >= 0.5 for q in qualities]
    return {f"{prefix}{i}": CaseResult(q, p) for i, (q, p) in enumerate(zip(qualities, flags, strict=True))}


def test_mcnemar_matches_hand_computed_exact_binomial_values() -> None:
    assert mcnemar_exact(1, 9) == pytest.approx(2 * (1 + 10) / 1024)
    assert mcnemar_exact(9, 1) == pytest.approx(2 * (1 + 10) / 1024)
    assert mcnemar_exact(0, 5) == pytest.approx(2 / 32)
    assert mcnemar_exact(5, 5) == 1.0  # a tie in the discordant cases: no evidence
    assert mcnemar_exact(0, 0) == 1.0  # no discordant case: no evidence
    assert mcnemar_exact(0, 1) == 1.0


def test_mcnemar_uses_a_normal_approximation_for_a_huge_number_of_discordant_cases() -> None:
    assert mcnemar_exact(1000, 1100) == pytest.approx(0.0307, abs=0.002)  # |100|/sqrt(2100) ~ 2.18 sigma
    assert mcnemar_exact(1050, 1000) == pytest.approx(0.279, abs=0.005)
    assert mcnemar_exact(5000, 5000) == 1.0
    assert mcnemar_exact(4000, 6000) < 1e-6


def test_a_case_is_the_mean_of_its_judged_runs_and_passes_when_most_runs_pass() -> None:
    assert case_result([1.0, 0.5, 0.0], [True, True, False]) == CaseResult(0.5, True)
    assert case_result([1.0, 0.0], [True, False]) == CaseResult(0.5, False)  # a tie is not a pass
    assert case_result([0.8], [True]) == CaseResult(0.8, True)
    assert case_result([], []) is None  # nothing judged: the case is left out


def test_the_same_gain_on_every_case_is_a_clear_difference_with_a_point_interval() -> None:
    better = results([0.7] * 20)
    worse = results([0.6] * 20)
    found = compare(better, worse, seed=1)
    assert found.label is Label.CLEAR
    assert found.first_better is True
    assert found.difference == pytest.approx(0.1)
    assert found.low == pytest.approx(0.1)
    assert found.high == pytest.approx(0.1)
    assert (found.cases, found.only_first, found.only_second) == (20, 0, 0)


def test_identical_results_have_an_interval_of_exactly_zero_and_no_clear_difference() -> None:
    same = results([0.2, 0.9, 0.5, 0.7, 0.4, 1.0, 0.0, 0.6, 0.3, 0.8, 0.55, 0.45])
    found = compare(same, dict(same), seed=3)
    assert (found.low, found.high, found.difference) == (0.0, 0.0, 0.0)
    assert found.label is Label.NONE
    assert found.first_better is None
    assert found.mcnemar_p == 1.0


def test_one_outlier_case_is_not_a_clear_difference() -> None:
    first = results([0.5] * 19 + [1.0])
    second = results([0.5] * 20)
    found = compare(first, second, seed=5)
    assert found.difference == pytest.approx(0.025)
    assert found.label is Label.NONE


def test_fewer_than_ten_common_cases_is_too_few_but_still_shows_the_numbers() -> None:
    nine = compare(results([1.0] * 9), results([0.0] * 9), seed=1)
    assert nine.label is Label.TOO_FEW
    assert (nine.low, nine.high) == (None, None)
    assert nine.difference == pytest.approx(1.0)
    assert nine.first_only_passed == 9
    ten = compare(results([1.0] * 10), results([0.0] * 10), seed=1)
    assert ten.label is Label.CLEAR
    empty = compare({}, {}, seed=1)
    assert empty.label is Label.TOO_FEW
    assert (empty.cases, empty.difference, empty.mcnemar_p) == (0, None, None)


def test_only_the_cases_both_sides_were_judged_on_are_compared_and_the_rest_are_counted() -> None:
    first = results([0.9] * 12, prefix="c")
    second = results([0.4] * 10, prefix="c")  # judged c0..c9 only
    second.update(results([0.4] * 3, prefix="z"))
    found = compare(first, second, seed=9)
    assert found.cases == 10
    assert (found.only_first, found.only_second) == (2, 3)
    assert found.label is Label.CLEAR


def test_the_pass_rate_detail_counts_cases_only_one_side_passed() -> None:
    first = results([1.0] * 6 + [0.0] * 6, [True] * 6 + [False] * 6)
    second = results([1.0] * 3 + [0.0] * 3 + [1.0] * 6, [True] * 3 + [False] * 3 + [True] * 6)
    found = compare(first, second, seed=2)
    assert found.pass_rate_first == pytest.approx(0.5)
    assert found.pass_rate_second == pytest.approx(0.75)
    assert (found.first_only_passed, found.second_only_passed) == (3, 6)


def test_same_data_gives_the_same_numbers_and_the_seed_ignores_the_order_of_ids() -> None:
    rng = np.random.default_rng(0)
    a = results(list(rng.random(40)))
    b = results(list(rng.random(40)))
    seed = seed_for("model-a", "model-b")
    assert seed == seed_for("model-b", "model-a")
    assert seed != seed_for("model-a", "model-c")
    assert compare(a, b, seed=seed) == compare(a, b, seed=seed)


def test_swapping_the_sides_negates_the_interval_and_keeps_the_label() -> None:
    rng = np.random.default_rng(1)
    for shift in (0.0, 0.05, 0.3):
        base = rng.random(30)
        a = results(list(np.clip(base + shift + rng.normal(0, 0.1, 30), 0, 1)))
        b = results(list(np.clip(base + rng.normal(0, 0.1, 30), 0, 1)))
        forward = compare(a, b, seed=7)
        backward = compare(b, a, seed=7)
        assert forward.label is backward.label
        assert forward.difference == pytest.approx(-(backward.difference or 0.0))
        assert forward.low == pytest.approx(-(backward.high or 0.0), abs=1e-12)
        assert forward.high == pytest.approx(-(backward.low or 0.0), abs=1e-12)
        assert (forward.first_only_passed, forward.second_only_passed) == (
            backward.second_only_passed,
            backward.first_only_passed,
        )
        assert forward.mcnemar_p == backward.mcnemar_p


def test_comparing_with_several_models_widens_the_interval() -> None:
    rng = np.random.default_rng(2)
    base = rng.random(40)
    a = results(list(np.clip(base + 0.05 + rng.normal(0, 0.1, 40), 0, 1)))
    b = results(list(np.clip(base + rng.normal(0, 0.1, 40), 0, 1)))
    one = compare(a, b, seed=4, comparisons=1)
    ten = compare(a, b, seed=4, comparisons=10)
    assert one.low is not None
    assert one.high is not None
    assert ten.low is not None
    assert ten.high is not None
    assert ten.low < one.low
    assert ten.high > one.high
    assert one.level == pytest.approx(0.95)
    assert ten.level == pytest.approx(0.995)
    assert compare(a, b, seed=4, comparisons=10_000).comparisons == sig.MAX_COMPARISONS


def test_compare_to_best_compares_every_other_model_with_the_best_and_adjusts_for_their_number() -> None:
    rng = np.random.default_rng(3)
    models: Mapping[str, Mapping[str, CaseResult]] = {
        "best": results([0.9] * 20),
        "close": results(list(np.clip(0.9 + rng.normal(0, 0.05, 20), 0, 1))),
        "far": results([0.2] * 20),
    }
    found = sig.compare_to_best(models, "best", seed_ids=["experiment"])
    assert set(found) == {"close", "far"}
    assert found["far"].label is Label.CLEAR
    assert found["far"].first_better is False  # the other model is worse than the best
    assert found["close"].comparisons == 2


def test_a_huge_run_keeps_the_work_bounded() -> None:
    n = 100_000
    rng = np.random.default_rng(4)
    a = results(list(rng.random(n)))
    b = results(list(rng.random(n)))
    assert sig._resamples(n) == sig.MIN_RESAMPLES
    assert sig._resamples(50) == sig.RESAMPLES
    started = time.perf_counter()
    found = compare(a, b, seed=1)
    assert time.perf_counter() - started < 10
    assert found.cases == n


def simulate(shift: float, runs: int, cases: int, seed: int) -> int:
    """How many of `runs` simulated comparisons the engine calls clear. Case difficulty is shared by the two
    sides (so the comparison is paired); each side adds its own noise."""
    rng = np.random.default_rng(seed)
    clear = 0
    for run in range(runs):
        difficulty = rng.random(cases)
        a = np.clip(difficulty + shift + rng.normal(0, 0.15, cases), 0, 1)
        b = np.clip(difficulty + rng.normal(0, 0.15, cases), 0, 1)
        found = compare(results(list(a)), results(list(b)), seed=seed * 1000 + run)
        clear += found.label is Label.CLEAR
    return clear


def test_the_widening_for_few_cases_fades_as_cases_grow() -> None:
    assert sig._expansion(10, 0.05) == pytest.approx(1.216, abs=0.01)  # t(9)/z x sqrt(10/9)
    assert sig._expansion(30, 0.05) < sig._expansion(10, 0.05)
    assert sig._expansion(100_000, 0.05) == pytest.approx(1.0, abs=0.001)


@pytest.mark.parametrize("cases", [10, 30, 50])
def test_calibration_no_true_difference_is_rarely_called_clear(cases: int) -> None:
    """Measured when written: 4.5 to 5.5 % of 400 for 10 to 100 cases (a plain percentile bootstrap gave 9 % at
    10 cases, which is why small runs are widened). The bound is the stated rate, 7 %."""
    assert simulate(shift=0.0, runs=400, cases=cases, seed=21) <= 0.07 * 400


def test_calibration_a_real_difference_is_found() -> None:
    assert simulate(shift=0.2, runs=100, cases=50, seed=12) >= 98  # measured 100 of 100
    assert simulate(shift=0.2, runs=100, cases=20, seed=13) >= 90  # measured 97 of 100
