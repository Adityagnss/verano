"""Terminal output. Messages go to stderr so stdout stays clean for values a script may capture."""

import typer

from verano.errors import CliError


def ok(message: str) -> None:
    typer.secho(f"✓ {message}", fg=typer.colors.GREEN, err=True)


def info(message: str) -> None:
    typer.echo(message, err=True)


def warn(message: str) -> None:
    typer.secho(f"! {message}", fg=typer.colors.YELLOW, err=True)


def fail(error: CliError) -> None:
    typer.secho(f"Error: {error.message}", fg=typer.colors.RED, err=True)
    if error.hint:
        typer.echo(error.hint, err=True)
