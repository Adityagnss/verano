"""
The `verano` command.

This file only parses the command line and prints; what each command does lives in its own
module, and every request goes through `ApiClient`, the public HTTP API.
"""

import os
import sys
import traceback
from pathlib import Path
from typing import Annotated

import click
import typer

from verano import __version__, apps, auth, push, runner, ui, validate
from verano import security as security_gate
from verano.config import DEFAULT_URL, ENV_URL
from verano.errors import CliError

app = typer.Typer(
    help="Set up and run prompt evaluations from your own codebase.",
    epilog="Start here: verano login, verano init, verano validate, verano push, verano run.",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode=None,
)
token_app = typer.Typer(help="Manage personal API tokens (for CI and scripts).", no_args_is_help=True)
app.add_typer(token_app, name="token")
app_cmd = typer.Typer(help="Connect your own app (over HTTP) and test it.", no_args_is_help=True)
app.add_typer(app_cmd, name="app")

Url = Annotated[
    str | None,
    typer.Option("--url", envvar=ENV_URL, help=f"Address of your Verano server (default {DEFAULT_URL})."),
]
Email = Annotated[str | None, typer.Option("--email", help="Your account email (asked for if left out).")]
PasswordStdin = Annotated[bool, typer.Option("--password-stdin", help="Read the password from standard input.")]
Days = Annotated[int, typer.Option("--days", min=1, max=365, help="How many days the token lasts.")]


def _version(show: bool) -> None:
    if show:
        typer.echo(f"verano {__version__}")
        raise typer.Exit()


@app.callback()
def root(
    version: Annotated[
        bool, typer.Option("--version", callback=_version, is_eager=True, help="Show the version and exit.")
    ] = False,
) -> None:
    pass


@app.command()
def login(
    url: Url = None,
    email: Email = None,
    password_stdin: PasswordStdin = False,
    token: Annotated[
        str | None, typer.Option("--token", help="Save a token you already have instead of signing in.")
    ] = None,
    days: Days = 90,
) -> None:
    """Sign in and save a personal API token on this machine."""
    auth.login(url, email, password_stdin, token, days)


FileOption = Annotated[
    Path | None, typer.Option("--file", "-f", help="The verano.yaml to use (default: ./verano.yaml).")
]


@app.command("init")
def init_command(
    path: Annotated[Path, typer.Argument(help="The folder that holds your code (default: here).")] = Path("."),
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Where to write (default: <folder>/verano.yaml).")
    ] = None,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Don't ask: include everything that can be tested.")] = False,
    force: Annotated[bool, typer.Option("--force", help="Replace an existing verano.yaml.")] = False,
    print_only: Annotated[bool, typer.Option("--print", help="Show the file instead of writing it.")] = False,
    include_tests: Annotated[bool, typer.Option("--include-tests", help="Also read test folders.")] = False,
) -> None:
    """Scan your code for prompts and write a verano.yaml. Nothing is sent anywhere."""
    from verano import init

    init.run(path, output, yes, force, print_only, include_tests)


@app.command("validate")
def validate_command(file: FileOption = None) -> None:
    """Check verano.yaml and show what `push` would set up. Nothing is sent anywhere."""
    validate.validate(file)


@app.command("push")
def push_command(
    name: Annotated[str | None, typer.Argument(help="Push only this prompt (default: all).")] = None,
    file: FileOption = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would change; change nothing.")] = False,
    no_data: Annotated[
        bool, typer.Option("--no-data", help="Leave the test cases alone (prompts, keys, models only).")
    ] = False,
    replace_draft: Annotated[
        bool, typer.Option("--replace-draft", help="Replace unapproved test cases made elsewhere with the file's.")
    ] = False,
    label: Annotated[
        str | None, typer.Option("--label", help="Point this label (for example staging) at the pushed version.")
    ] = None,
) -> None:
    """Create or update the projects, keys, models, prompts and test cases described in verano.yaml."""
    push.command(file, name, dry_run, not no_data, replace_draft, label)


@app.command("run")
def run_command(
    name: Annotated[str | None, typer.Argument(help="Run only this prompt (default: all).")] = None,
    file: FileOption = None,
    ci: Annotated[
        bool, typer.Option("--ci", help="For pipelines: never ask, and exit 2 if the quality gate fails.")
    ] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Start without asking after showing the cost.")] = False,
    max_cost: Annotated[
        float | None,
        typer.Option("--max-cost", min=0, help="Refuse to start if the estimate is above this many dollars."),
    ] = None,
    timeout: Annotated[int, typer.Option("--timeout", min=10, help="Seconds to wait for each run.")] = int(
        runner.TIMEOUT_S
    ),
    json_output: Annotated[bool, typer.Option("--json", help="Print the results as JSON on standard output.")] = False,
    baseline: Annotated[
        str | None,
        typer.Option("--baseline", help="Compare with this earlier run (its id) instead of the latest comparable run."),
    ] = None,
    markdown_file: Annotated[
        Path | None, typer.Option("--markdown-file", help="Also write the results table, as Markdown, to this file.")
    ] = None,
    security: Annotated[
        bool, typer.Option("--security", help="Also run the approved security pack and gate on its pass rates.")
    ] = False,
    security_min: Annotated[
        float | None,
        typer.Option("--security-min", min=0, max=1, help="Lowest share of attacks resisted (default 0.8)."),
    ] = None,
) -> None:
    """Run each prompt on its test cases, print the results and a link."""
    quality_error: CliError | None = None
    try:
        runner.command(file, name, ci, yes, max_cost, timeout, json_output, baseline, markdown_file)
    except CliError as error:
        quality_error = error
        if not security:
            raise
    if security:
        security_gate.command(file, name, ci, timeout, security_min)
    if quality_error is not None:
        raise quality_error


@app.command("status")
def status_command(
    name: Annotated[str | None, typer.Argument(help="Show only this prompt (default: all).")] = None,
    file: FileOption = None,
) -> None:
    """Show the latest results of each prompt."""
    runner.status_command(file, name)


@app.command()
def logout() -> None:
    """Revoke the saved token and delete it from this machine."""
    auth.logout()


@app.command()
def whoami() -> None:
    """Show who you are signed in as, and to which server."""
    auth.whoami()


@token_app.command("create")
def token_create(
    name: Annotated[str, typer.Option("--name", help="What the token is for, for example ci.")],
    url: Url = None,
    email: Email = None,
    password_stdin: PasswordStdin = False,
    days: Days = 90,
    never_expires: Annotated[bool, typer.Option("--never-expires", help="The token does not expire.")] = False,
    read_only: Annotated[
        bool, typer.Option("--read-only", help="The token can look and fetch prompts but change nothing.")
    ] = False,
    project: Annotated[str | None, typer.Option("--project", "-p", help="Only for this project (its name).")] = None,
) -> None:
    """Create a token for CI. It is printed once; set it as VERANO_API_TOKEN."""
    auth.create_token(name, url, email, password_stdin, None if never_expires else days, read_only, project)


@token_app.command("list")
def token_list() -> None:
    """List your tokens."""
    auth.list_tokens()


@token_app.command("revoke")
def token_revoke(token_id: Annotated[str, typer.Argument(help="The id shown by `verano token list`.")]) -> None:
    """Revoke a token so it stops working."""
    auth.revoke_token(token_id)


ProjectName = Annotated[str, typer.Option("--project", "-p", help="The project's name in Verano.")]


@app_cmd.command("list")
def app_list(project: ProjectName) -> None:
    """List the apps connected to a project."""
    apps.list_command(project)


@app_cmd.command("add")
def app_add(
    project: ProjectName,
    name: Annotated[str, typer.Option("--name", help="What to call the app.")],
    url: Annotated[str, typer.Option("--url", help="The address Verano sends each test case to.")],
    template: Annotated[
        str, typer.Option("--template", help="The JSON to send, for example '{\"question\": {{ question | tojson }}}'.")
    ],
    answer_path: Annotated[str, typer.Option("--answer-path", help="Where the answer is in the reply, e.g. $.answer.")],
    chunks_path: Annotated[
        str | None, typer.Option("--chunks-path", help="Where the retrieved text is, e.g. $.sources[*].text.")
    ] = None,
    tool_calls_path: Annotated[
        str | None, typer.Option("--tool-calls-path", help="Where the tool calls are, e.g. $.tool_calls.")
    ] = None,
    cost_path: Annotated[str | None, typer.Option("--cost-path", help="Where the app reports its cost.")] = None,
    conversation: Annotated[
        bool, typer.Option("--conversation", help="Talk to the app turn by turn with a simulated user.")
    ] = False,
    bearer_env: Annotated[
        str | None, typer.Option("--bearer-env", help="Name of an environment variable holding a bearer token.")
    ] = None,
) -> None:
    """Connect an app to a project."""
    apps.add_command(
        project, name, url, template, answer_path, chunks_path, tool_calls_path, cost_path, conversation, bearer_env
    )


@app_cmd.command("test")
def app_test(
    project: ProjectName,
    name: Annotated[str, typer.Argument(help="The app's name.")],
    input: Annotated[list[str], typer.Option("--input", "-i", help="One input, name=value. Repeat for more.")],
) -> None:
    """Send one test case to an app and show what was sent, what came back and what Verano read."""
    apps.test_command(project, name, input)


@app.command("mcp")
def mcp_command(
    allow_write: Annotated[
        bool,
        typer.Option(
            "--allow-write", help="Let the agent create projects, start runs, accept improvements and move labels."
        ),
    ] = False,
    max_cost: Annotated[
        float | None,
        typer.Option("--max-cost", min=0, help="The most a run started by the agent may cost, in dollars."),
    ] = None,
) -> None:
    """Start a local MCP server (standard input and output) so an AI agent can use Verano with your token."""
    from verano.mcp import serve

    serve.command(allow_write, max_cost)


def main() -> None:
    try:
        app(standalone_mode=False)
    except CliError as error:
        ui.fail(error)
        sys.exit(error.exit_code)
    except KeyboardInterrupt:
        ui.info("Cancelled.")
        sys.exit(130)
    except click.exceptions.Exit as stop:
        sys.exit(stop.exit_code)
    except click.exceptions.Abort:
        ui.info("Cancelled.")
        sys.exit(130)
    except click.ClickException as error:
        error.show()
        sys.exit(error.exit_code)
    except Exception as error:
        ui.fail(CliError(f"Something unexpected went wrong: {error}", "Set VERANO_DEBUG=1 to see the details."))
        if os.environ.get("VERANO_DEBUG"):
            traceback.print_exc()
        sys.exit(1)
