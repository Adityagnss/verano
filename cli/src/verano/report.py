"""How results look in the terminal: money, percentages and one table per run."""

from decimal import Decimal
from typing import Any


def money(value: str | float | Decimal | None) -> str:
    if value is None:
        return "price unknown"
    amount = Decimal(str(value))
    if amount == 0:
        return "$0"
    return f"${amount:.4f}" if amount < Decimal("0.01") else f"${amount:.2f}"


def percent(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.0f}%"


def millis(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value / 1000:.1f}s" if value >= 1000 else f"{value:.0f}ms"


def results_table(models: list[dict[str, Any]]) -> list[str]:
    header = ["Model", "Quality", "Passed", "Same answer", "Avg time", "Cost/call", "Failed calls"]
    rows = [
        [
            m["model"],
            percent(m["quality"]) + (f" ({m['judged_cases']}/{m['cases']} judged)" if m.get("unscored_cases") else ""),
            percent(m["pass_rate"]),
            percent(m.get("stability")) if m.get("stability") is not None else "needs 2+ runs",
            millis(m.get("latency_ms")),
            money(m.get("cost_per_call")),
            str(m.get("failed_calls", 0)),
        ]
        for m in models
    ]
    widths = [max(len(row[i]) for row in [header, *rows]) for i in range(len(header))]
    lines = ["  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)).rstrip() for row in [header, *rows]]
    lines.insert(1, "  ".join("-" * w for w in widths))
    return lines
