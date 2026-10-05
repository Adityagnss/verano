"""
`verano init`: scan the code, show what was found, and write verano.yaml.

The scan runs on this machine and sends nothing anywhere. Every finding is shown with its file and
line; the ones that can be tested are ticked, the rest are listed with the reason, and what could
not be read is counted and named, never guessed.
"""

import re
import sys
from pathlib import Path

import typer

from verano import ui
from verano.errors import CliError
from verano.loader import FILENAME
from verano.scan.findings import Entry, ScanResult, to_entry
from verano.scan.render import render
from verano.scan.run import scan

LEVEL = "Python, TypeScript and JavaScript are read with syntax trees (high accuracy). Nothing leaves your machine."
BROAD_LEVEL = "Other languages are found by clues (medium accuracy), so those findings are never ticked for you."
HIGH = {"Python", "TypeScript/JavaScript"}


def summary(result: ScanResult) -> str:
    counts = ", ".join(f"{n} {language}" for language, n in sorted(result.by_language.items()))
    return f"{result.files_scanned} file{'s' if result.files_scanned != 1 else ''}" + (f" ({counts})" if counts else "")


def describe(entry: Entry) -> str:
    f = entry.finding
    parts = [p for p in (f.provider, f.model or "model not found") if p]
    if "temperature" in f.params:
        parts.append(f"temperature {f.params['temperature']}")
    inputs = len(f.variables)
    parts.append(f"{inputs} input{'s' if inputs != 1 else ''}")
    return " · ".join(parts)


def show(result: ScanResult, entries: list[Entry], ticked: set[int]) -> None:
    ui.info(f"Scanned {summary(result)}. {LEVEL}")
    if set(result.by_language) - HIGH:
        ui.info(BROAD_LEVEL)
    unreadable = [e for e in entries if not e.finding.usable]
    found = len(entries)
    ui.info(f"Found {found} prompt{'s' if found != 1 else ''}; could not read {len(unreadable)}.")
    for number, entry in enumerate(entries, start=1):
        mark = "[x]" if number - 1 in ticked else "[ ]"
        ui.info(f" {mark} {number:>2}  {entry.name:<28} {entry.finding.where:<34} {describe(entry)}")
        if entry.reason:
            ui.info(f"        not ready: {entry.reason}")
        for note in entry.finding.notes:
            ui.info(f"        note: {note}")
    for note in result.other[:10]:
        ui.info(f"  also found: {note} (Verano can't test this yet)")
    if result.data_files:
        ui.info("  possible test data: " + ", ".join(result.data_files) + " (set `data.cases` in the file)")
    for skipped in result.files_skipped[:10]:
        ui.warn(f"skipped {skipped}")


def parse_choice(answer: str, count: int, default: set[int]) -> set[int]:
    text = answer.strip().lower()
    if text in {"", "all"}:
        return set(default)
    if text == "none":
        return set()
    chosen: set[int] = set()
    for part in re.split(r"[,\s]+", text):
        if not part.isdigit() or not 1 <= int(part) <= count:
            raise CliError(
                f"'{part}' is not one of the numbers 1 to {count}.", "Write numbers like 1,3, or all, or none."
            )
        chosen.add(int(part) - 1)
    return chosen


def run(path: Path, output: Path | None, yes: bool, force: bool, print_only: bool, include_tests: bool) -> None:
    root = path.resolve()
    if not root.is_dir():
        raise CliError(f"{path} is not a folder.", "Pass the folder that holds your code, for example `verano init .`")
    target = output or root / FILENAME
    if target.exists() and not force and not print_only:
        raise CliError(f"{target.name} already exists.", "Use --force to replace it, or -o to write a different file.")
    result = scan(root, include_tests)
    taken: set[str] = set()
    entries = [to_entry(f, taken) for f in result.findings if f.has_prompt or f.problems]
    if not entries:
        ui.info(f"Scanned {summary(result)}. {LEVEL}")
        ui.info("No LLM calls with a prompt were found.")
        ui.info("Verano reads Python, TypeScript, JavaScript, Java, Go, C#, Ruby, PHP, Rust, Kotlin and Swift.")
        ui.info("For any other language, or prompts kept in text files, write verano.yaml by hand.")
        return
    default = {i for i, e in enumerate(entries) if e.runnable}
    show(result, entries, default)
    interactive = not yes and sys.stdin.isatty() and sys.stderr.isatty()
    ticked = default
    if interactive:
        answer = typer.prompt("Include which? (numbers like 1,3 · all · none)", default="all", err=True)
        ticked = parse_choice(answer, len(entries), default)
    chosen = [e for i, e in enumerate(entries) if i in ticked and e.finding.usable]
    blocked = [e for i, e in enumerate(entries) if i in ticked and not e.finding.usable]
    for entry in blocked:
        ui.warn(f"{entry.name}: left out, it could not be read ({entry.reason}).")
    if not chosen:
        ui.info("Nothing was ticked, so no file was written.")
        return
    skipped = [e for e in entries if e not in chosen]
    text = render(re.sub(r"[^\w .-]+", "-", root.name).strip("-") or "project", chosen, skipped)
    if print_only:
        typer.echo(text, nl=False)
        return
    target.write_text(text, encoding="utf-8")
    ui.ok(f"Wrote {target} with {len(chosen)} prompt{'s' if len(chosen) != 1 else ''}.")
    ui.info("Next: fill in every TODO (task, models, your examples under `data:`), then")
    ui.info("  verano validate        check the file")
    ui.info("  verano push --dry-run  see what would be set up")
