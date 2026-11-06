"""
`verano app`: connect your own application to a project and try one test case against it.

An app is reached over HTTP. You give its address, the request to send (JSON, with `{{ name | tojson }}` where a
test case's input goes) and where in its reply the answer, the retrieved text and the tool calls are. `app test`
shows exactly what was sent and what came back, so the mapping can be fixed before a run. Secrets are read from
environment variables, never from the command line or a file.
"""

import json
import os
from typing import Any

import typer

from verano import auth, ui
from verano.errors import CliError
from verano.runner import find_project

NOT_FOUND = "This project has no app called '{name}'."


def _app_by_name(api: Any, project_id: str, name: str) -> dict[str, Any]:
    found = next((a for a in api.get(f"/projects/{project_id}/apps") if a["name"] == name), None)
    if found is None:
        raise CliError(NOT_FOUND.format(name=name), "List them with `verano app list`.")
    app: dict[str, Any] = found
    return app


def parse_inputs(pairs: list[str]) -> dict[str, str]:
    """`name=value` pairs into the inputs of one test case."""
    inputs = {}
    for pair in pairs:
        name, separator, value = pair.partition("=")
        if not separator or not name.strip():
            raise CliError(
                f"'{pair}' is not name=value.", "Write each input as --input question='How long is shipping?'"
            )
        inputs[name.strip()] = value
    return inputs


def list_command(project: str) -> None:
    api = auth.client()
    for app in api.get(f"/projects/{find_project(api, project)['id']}/apps"):
        typer.echo(f"{app['name']}  {app['method']} {app['url']}  ({app['mode']})")


def add_command(
    project: str,
    name: str,
    url: str,
    template: str,
    answer_path: str,
    chunks_path: str | None,
    tool_calls_path: str | None,
    cost_path: str | None,
    conversation: bool,
    bearer_env: str | None,
) -> None:
    api = auth.client()
    pid = str(find_project(api, project)["id"])
    body: dict[str, Any] = {
        "name": name,
        "url": url,
        "request_template": template,
        "answer_path": answer_path,
        "chunks_path": chunks_path,
        "tool_calls_path": tool_calls_path,
        "cost_path": cost_path,
        "mode": "conversation" if conversation else "single",
    }
    if bearer_env:
        token = os.environ.get(bearer_env, "").strip()
        if not token:
            raise CliError(f"The environment variable {bearer_env} is not set or is empty.")
        body |= {"auth_kind": "bearer", "bearer_token": token}
    created = api.post(f"/projects/{pid}/apps", body)
    ui.ok(f"App '{created['name']}' added. Select it next to your models on the Run step, or in verano.yaml.")


def test_command(project: str, name: str, inputs: list[str]) -> None:
    api = auth.client()
    pid = str(find_project(api, project)["id"])
    app = _app_by_name(api, pid, name)
    shown = api.post(f"/projects/{pid}/apps/{app['id']}/test", {"inputs": parse_inputs(inputs)})
    typer.echo("Sent:")
    typer.echo(shown["request_body"] or "(nothing: the request template could not be filled in)")
    typer.echo(f"\nReceived (status {shown['status_code']}, {shown['latency_ms']} ms):")
    typer.echo((shown["response_body"] or "")[:2000])
    if shown["error"]:
        ui.warn(shown["error"])
        raise typer.Exit(1)
    reply = shown["reply"]
    typer.echo("\nVerano read:")
    typer.echo(f"  answer:     {reply['answer']}")
    typer.echo(f"  chunks:     {json.dumps(reply['chunks'], ensure_ascii=False)}")
    typer.echo(f"  tool calls: {json.dumps(reply['tool_calls'], ensure_ascii=False)}")
