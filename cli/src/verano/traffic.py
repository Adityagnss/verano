"""
`verano traffic`: bring real traces into a project and look at them.

`import` sends an export file (OpenTelemetry, HAR, Langfuse, Phoenix or LangSmith) to the project's Traffic step, which
removes personal data before storing anything, and prints what was read, skipped and cleaned. `list` shows the stored
traces, newest first, with the same filters as the screen.
"""

from pathlib import Path
from typing import Any

import typer

from verano import auth, ui
from verano.errors import CliError
from verano.runner import find_project

READ_FAILED = "Can't read {path}: {reason}."
SHOWN_PROBLEMS = 10


def _trace_path(project_id: str) -> str:
    return f"/projects/{project_id}/traffic"


def import_command(project: str, path: Path, format_name: str, prompt_version: str | None) -> None:
    try:
        content = path.read_bytes()
    except OSError as error:
        raise CliError(READ_FAILED.format(path=path, reason=error.strerror or "unreadable")) from error
    api = auth.client()
    pid = str(find_project(api, project)["id"])
    data = {"format": format_name, **({"prompt_version": prompt_version} if prompt_version else {})}
    report: dict[str, Any] = api.request(
        "POST", f"{_trace_path(pid)}/import", files={"file": (path.name, content, "application/json")}, data=data
    )
    ui.ok(f"Read {report['found']} records as {report['format_label']}: {report['imported']} new traces stored.")
    if report["duplicates"]:
        ui.info(f"{report['duplicates']} were already stored and were skipped.")
    if report["ignored"]:
        ui.info(f"{report['ignored']} records were not model calls and were ignored.")
    if report["scrubbed"]:
        ui.info(f"{report['scrubbed']} pieces of personal data were replaced before storing.")
    if report["truncated"]:
        ui.info(f"{report['truncated']} traces were longer than the size limit and were cut.")
    for problem in report["problems"][:SHOWN_PROBLEMS]:
        ui.warn(f"Record {problem['record']}: {problem['message']}")
    hidden = max(0, len(report["problems"]) - SHOWN_PROBLEMS) + report["more_problems"]
    if hidden:
        ui.warn(f"{hidden} more records had problems.")


def list_command(
    project: str, limit: int, failed: bool, low_rated: bool, source: str | None, query: str | None
) -> None:
    api = auth.client()
    pid = str(find_project(api, project)["id"])
    params: dict[str, Any] = {"limit": limit, "source": source, "q": query}
    if failed:
        params["failed"] = "true"
    if low_rated:
        params["low_rated"] = "true"
    page = api.get(_trace_path(pid), **params)
    if not page["items"]:
        typer.echo("No traces yet. Import a file with `verano traffic import`.")
        return
    for item in page["items"]:
        mark = "FAILED" if item["status"] == "error" else "ok"
        question = " ".join(item["input_preview"].split())[:70]
        typer.echo(f"{item['started_at'][:19]}  {item['source']:<9} {mark:<6} {question}")
