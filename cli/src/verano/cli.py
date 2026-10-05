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

from verano import __version__, auth, ui, validate
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


@app.command("validate")
def validate_command(file: FileOption = None) -> None:
    """Check verano.yaml and show what `push` would set up. Nothing is sent anywhere."""
    validate.validate(file)


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
        sys.exit(1)
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
