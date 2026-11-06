"""How results look in the terminal: money, percentages and one table per run (with the significance label)."""

from collections.abc import Iterable
from decimal import Decimal
from typing import Any

COMMENT_MARKER = "<!-- verano-run-results -->"


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


def markdown_summary(results: Iterable[Any]) -> str:
    """The run as a Markdown comment for a pull request: one table per prompt, the gate's verdict and a link.
    It starts with a hidden marker so a CI job can find and update its earlier comment instead of adding another."""
    lines = [COMMENT_MARKER, "## Verano prompt check", ""]
    for result in results:
        verdict = result.verdict
        if result.error:
            state = "error"
        elif verdict is None:
            state = "no gate set"
        else:
            state = "passed" if verdict.passed else "failed"
        lines += [f"### {result.name} ({state})", ""]
        if result.error:
            lines += [f"The run could not finish: {result.error}", ""]
            continue
        lines += ["| Model | Quality | Passed | Avg time | Cost per call |", "| --- | --- | --- | --- | --- |"]
        for m in result.models:
            lines.append(
                f"| {m['model']} | {percent(m['quality'])} | {percent(m['pass_rate'])} "
                f"| {millis(m.get('latency_ms'))} | {money(m.get('cost_per_call'))} |"
            )
        lines.append("")
        if verdict is not None:
            lines += [f"- {failure}" for failure in verdict.failures] + [f"- _{note}_" for note in verdict.notes]
            lines.append("")
        if result.link:
            lines += [f"[Open the full results]({result.link})", ""]
    return "\n".join(lines).rstrip() + "\n"
