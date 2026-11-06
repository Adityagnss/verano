"""Starts the MCP server for `verano mcp`: reads the saved sign-in, says on standard error how it was started."""

import sys
from decimal import Decimal

from verano import auth, ui
from verano.client import ApiClient
from verano.mcp.protocol import Server
from verano.mcp.tools import WRITE_FLAG, Context


def command(allow_write: bool, max_cost: float | None) -> None:
    credentials = auth.signed_in()
    context = Context(
        ApiClient.from_credentials(credentials),
        credentials.url,
        allow_write,
        Decimal(str(max_cost)) if max_cost is not None else None,
    )
    mode = (
        f"can change things ({WRITE_FLAG})" if allow_write else f"read-only (add {WRITE_FLAG} to let it change things)"
    )
    ui.info(f"Verano MCP server for {credentials.url}: {mode}. Waiting for an agent on standard input.")
    Server(context).serve(sys.stdin, sys.stdout, ui.info)
