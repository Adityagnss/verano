"""
The quality gate of `verano run --ci`: did this run meet what the prompt's `gate:` demands?

Checked per model, so one weak model can't hide behind a strong one. A run that stopped early
(budget, error, cancelled) fails the gate: its numbers say nothing about quality. So does a run
with answers the judge could not score: those are left out of the numbers, so what is left may
flatter the model. `max_drop`
compares with the most recent earlier run of the same models and settings on the same test
cases (the prompt may differ: that is the point); with nothing to compare against it is noted,
not failed, so the first run can set the baseline.
"""

from dataclasses import dataclass
from typing import Any

from verano.spec import Gate

Baseline = dict[str, dict[str, float | None]]  # per model: quality, cost_per_call, latency_ms


@dataclass(frozen=True)
class Verdict:
    failures: list[str]
    notes: list[str]

    @property
    def passed(self) -> bool:
        return not self.failures


def percent(value: float) -> str:
    return f"{value * 100:.0f}%"


def money(value: float) -> str:
    return f"${value:.4f}" if value < 0.01 else f"${value:.2f}"


def evaluate(
    gate: Gate,
    models: list[dict[str, Any]],
    finished: bool,
    stop_reason: str | None,
    baseline: dict[str, float] | None,
    baseline_metrics: Baseline | None = None,
) -> Verdict:
    failures: list[str] = []
    notes: list[str] = []
    if not finished:
        why = f" ({stop_reason.rstrip('.')})" if stop_reason else ""
        failures.append(f"The run stopped early{why}, so its scores can't be trusted.")
    for model in models:
        name = model["model"]
        unscored = int(model.get("unscored_cases") or 0)
        if unscored:
            failures.append(f"{name}: {unscored} answers could not be judged, so its scores can't be trusted.")
        if model["quality"] is None or model["pass_rate"] is None:
            if not unscored:
                failures.append(f"{name}: nothing could be scored.")
            continue
        quality, passed = float(model["quality"]), float(model["pass_rate"])
        if gate.min_quality is not None and quality < gate.min_quality:
            failures.append(f"{name}: quality {percent(quality)} is below the minimum {percent(gate.min_quality)}.")
        if gate.min_pass_rate is not None and passed < gate.min_pass_rate:
            failures.append(f"{name}: {percent(passed)} passed, below the minimum {percent(gate.min_pass_rate)}.")
        if gate.max_drop is not None:
            before = (baseline or {}).get(name)
            if before is None:
                notes.append(f"{name}: no earlier run to compare with, so the drop was not checked.")
            elif before - quality > gate.max_drop + 1e-9:
                points = (before - quality) * 100
                failures.append(
                    f"{name}: quality fell {points:.0f} points ({percent(before)} → {percent(quality)}); "
                    f"at most {gate.max_drop * 100:.0f} allowed."
                )
        _check_cost_and_speed(gate, model, baseline_metrics, failures, notes)
    return Verdict(failures, notes)


def _check_cost_and_speed(
    gate: Gate, model: dict[str, Any], baseline: Baseline | None, failures: list[str], notes: list[str]
) -> None:
    name = model["model"]
    cost, latency = model.get("cost_per_call"), model.get("latency_ms")
    earlier = (baseline or {}).get(name) or {}
    if gate.max_cost_per_call is not None and cost is not None and float(cost) > gate.max_cost_per_call + 1e-12:
        failures.append(f"{name}: costs {money(float(cost))} a call, above the limit {money(gate.max_cost_per_call)}.")
    if gate.max_latency_ms is not None and latency is not None and float(latency) > gate.max_latency_ms:
        failures.append(
            f"{name}: answers take {float(latency) / 1000:.1f}s on average, above the limit "
            f"{gate.max_latency_ms / 1000:.1f}s."
        )
    for limit, now, before, what in (
        (gate.max_cost_increase, cost, earlier.get("cost_per_call"), "costs"),
        (gate.max_slowdown, latency, earlier.get("latency_ms"), "takes"),
    ):
        if limit is None or now is None:
            continue
        if before is None or float(before) <= 0:
            notes.append(f"{name}: no earlier run to compare with, so what it {what} was not checked.")
        elif float(now) > float(before) * (1 + limit) + 1e-12:
            grew = (float(now) / float(before) - 1) * 100
            failures.append(
                f"{name}: what it {what} grew {grew:.0f}% against the baseline; at most {limit * 100:.0f}% allowed."
            )
