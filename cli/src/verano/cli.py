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

from verano import __version__, auth, push, runner, ui, validate
from verano.config import DEFAULT_URL, ENV_URL
from verano.errors import CliError

app = typer.Typer(
    help="Set up and run prompt evaluations from your own codebase.",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode=None,
)
token_app = typer.Typer(help="Manage personal API tokens (for CI and scripts).", no_args_is_help=True)
app.add_typer(token_app, name="token")

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
) -> None:
    """Create or update the projects, keys, models, prompts and test cases described in verano.yaml."""
    push.command(file, name, dry_run, not no_data, replace_draft)


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
) -> None:
    """Run each prompt on its test cases, print the results and a link."""
    runner.command(file, name, ci, yes, max_cost, timeout, json_output)


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
) -> None:
    """Create a token for CI. It is printed once; set it as VERANO_API_TOKEN."""
    auth.create_token(name, url, email, password_stdin, None if never_expires else days)


@token_app.command("list")
def token_list() -> None:
    """List your tokens."""
    auth.list_tokens()


@token_app.command("revoke")
def token_revoke(token_id: Annotated[str, typer.Argument(help="The id shown by `verano token list`.")]) -> None:
    """Revoke a token so it stops working."""
    auth.revoke_token(token_id)


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
