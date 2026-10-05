"""
The quality gate of `verano run --ci`: did this run meet what the prompt's `gate:` demands?

Checked per model, so one weak model can't hide behind a strong one. A run that stopped early
(budget, error, cancelled) fails the gate: its numbers say nothing about quality. `max_drop`
compares with the most recent earlier run of the same models and settings on the same test
cases (the prompt may differ: that is the point); with nothing to compare against it is noted,
not failed, so the first run can set the baseline.
"""

from dataclasses import dataclass
from typing import Any

from verano.spec import Gate


@dataclass(frozen=True)
class Verdict:
    failures: list[str]
    notes: list[str]

    @property
    def passed(self) -> bool:
        return not self.failures


def percent(value: float) -> str:
    return f"{value * 100:.0f}%"


def evaluate(
    gate: Gate,
    models: list[dict[str, Any]],
    finished: bool,
    stop_reason: str | None,
    baseline: dict[str, float] | None,
) -> Verdict:
    failures: list[str] = []
    notes: list[str] = []
    if not finished:
        why = f" ({stop_reason.rstrip('.')})" if stop_reason else ""
        failures.append(f"The run stopped early{why}, so its scores can't be trusted.")
    for model in models:
        name = model["model"]
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
    return Verdict(failures, notes)
