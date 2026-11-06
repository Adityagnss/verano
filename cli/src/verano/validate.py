"""`verano validate`: check a verano.yaml and show what `push` would set up."""

from pathlib import Path

import typer

from verano import ui
from verano.loader import Loaded, ResolvedPrompt, find_file, load


def describe(prompt: ResolvedPrompt, root: Path) -> list[str]:
    entry = prompt.entry
    parts = [part for part, text in (("system", prompt.system), ("user", prompt.user)) if text]
    names = ", ".join(prompt.variables) or "none"
    lines = [
        f'{entry.name}  →  project "{prompt.project_name}"',
        f"    prompt:  {' + '.join(parts)} (variables I can see: {names})",
        f"    task:    {entry.task.type}"
        + (f", {len(entry.task.allowed_outputs)} allowed outputs" if entry.task.allowed_outputs else ""),
        f"    models:  {', '.join(entry.models)}"
        + (f" (judge: {entry.judge})" if entry.judge else "")
        + f" · {entry.runs} run{'s' if entry.runs != 1 else ''}",
    ]
    gate = entry.gate
    if gate is not None:
        checks = [
            f"{label} {value * 100:.0f}%"
            for label, value in (
                ("min quality", gate.min_quality),
                ("min pass rate", gate.min_pass_rate),
                ("max drop", gate.max_drop),
            )
            if value is not None
        ]
        if gate.max_cost_per_call is not None:
            checks.append(f"max cost per call ${gate.max_cost_per_call:g}")
        if gate.max_latency_ms is not None:
            checks.append(f"max average time {gate.max_latency_ms / 1000:g}s")
        if gate.max_cost_increase is not None:
            checks.append(f"cost may grow {gate.max_cost_increase * 100:.0f}%")
        if gate.max_slowdown is not None:
            checks.append(f"time may grow {gate.max_slowdown * 100:.0f}%")
        if gate.baseline:
            checks.append(f"baseline run {gate.baseline}")
        lines.append(f"    gate:    {', '.join(checks)} (enforced by `verano run --ci`)")
    data = []
    if prompt.cases is not None:
        skipped = len(prompt.cases.skipped)
        source = prompt.entry.data.cases.file if prompt.entry.data.cases else ""
        data.append(
            f"{len(prompt.cases.cases)} test cases from {source}" + (f" ({skipped} rows skipped)" if skipped else "")
        )
    if prompt.golden:
        data.append(f"golden {prompt.golden.relative_to(root.resolve())}")
    if prompt.inputs:
        data.append(f"{len(prompt.inputs)} input file{'s' if len(prompt.inputs) != 1 else ''}")
    lines.append(f"    data:    {'; '.join(data) if data else 'none'}")
    if entry.source:
        lines.append(f"    from:    {entry.source.file}" + (f":{entry.source.line}" if entry.source.line else ""))
    return lines


def validate(file: Path | None) -> Loaded:
    loaded = load(file or find_file())
    count = len(loaded.prompts)
    ui.ok(
        f"{loaded.path.name} is valid: {count} prompt{'s' if count != 1 else ''}, each becomes its own Verano project."
    )
    for prompt in loaded.prompts:
        for line in describe(prompt, loaded.root):
            typer.echo(line)
    for note in loaded.warnings:
        ui.warn(note)
    return loaded
