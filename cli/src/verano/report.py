"""How results look in the terminal: money, percentages and one table per run (with the significance label)."""

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


def versus_best(m: dict[str, Any], best: bool) -> str:
    """How a model compares with the best one on quality, in the engine's own words and with the difference."""
    compared = m.get("vs_best")
    if compared is None:
        return "best" if best else "—"
    gap = f" ({compared['difference'] * 100:+.0f}%)" if compared.get("difference") is not None else ""
    return f"{compared['label']}{gap}"


def results_table(models: list[dict[str, Any]]) -> list[str]:
    compared = any(m.get("vs_best") for m in models)
    header = ["Model", "Quality", "Passed", "Same answer", "Avg time", "Cost/call", "Failed calls"]
    if compared:
        header.insert(3, "Vs the best")
    top = max((m["quality"] for m in models if m["quality"] is not None), default=None)
    rows = [
        [
            m["model"],
            percent(m["quality"]) + (f" ({m['judged_cases']}/{m['cases']} judged)" if m.get("unscored_cases") else ""),
            percent(m["pass_rate"]),
            *([versus_best(m, m["quality"] == top)] if compared else []),
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
