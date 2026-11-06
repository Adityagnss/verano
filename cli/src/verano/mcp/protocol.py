"""
The MCP wire protocol, by hand: JSON-RPC 2.0, one message per line on standard input and output.

Handles `initialize`, `ping`, `tools/list` and `tools/call`; notifications are accepted and ignored.
Tool input is validated against the tool's schema before the tool runs, and its output is validated
against the output schema before it is returned, so what an agent gets always matches what it was
told to expect. Nothing is ever written to standard output except protocol messages.
"""

import json
from collections.abc import Callable
from typing import Any, TextIO

from pydantic import ValidationError

from verano import __version__
from verano.mcp.tools import REFUSAL, WRITE_FLAG, Context, Refused, Tool, registry

SUPPORTED_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND, INVALID_PARAMS = -32700, -32600, -32601, -32602
INSTRUCTIONS = (
    "Verano tests and improves LLM prompts. Read results with get_result: it includes the evidence (the weakest "
    "answers) and the limits of the numbers, so say what the limits are when you report them. Tools that change "
    "or spend anything need the person to have started this server with --allow-write; if one is refused, tell "
    "them which flag to add instead of trying another way."
)


def _error(identifier: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": identifier, "error": {"code": code, "message": message}}


def _plain(message: str, is_error: bool = True) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": message}], "isError": is_error}


def _problems(error: ValidationError) -> str:
    parts = []
    for item in error.errors():
        where = ".".join(str(p) for p in item["loc"]) or "arguments"
        parts.append(f"{where}: {item['msg']}")
    return "; ".join(parts)


class Server:
    def __init__(self, context: Context, tools: list[Tool] | None = None) -> None:
        self.context = context
        self.tools = {tool.name: tool for tool in (tools if tools is not None else registry())}

    def describe(self, tool: Tool) -> dict[str, Any]:
        suffix = "" if not tool.writes else " Needs the server to be started with --allow-write."
        return {
            "name": tool.name,
            "title": tool.title,
            "description": tool.description + suffix,
            "inputSchema": tool.input_model.model_json_schema(),
            "outputSchema": tool.output_model.model_json_schema(),
            "annotations": {"readOnlyHint": not tool.writes, "destructiveHint": False, "openWorldHint": False},
        }

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        tool = self.tools.get(name)
        if tool is None:
            return _plain(f"There is no tool called {name}. Use tools/list to see the available ones.")
        if tool.writes and not self.context.allow_write:
            return _plain(REFUSAL.format(tool=tool.name, flag=WRITE_FLAG))
        try:
            given = tool.input_model.model_validate(arguments)
        except ValidationError as error:
            return _plain(f"The arguments for {name} are not valid: {_problems(error)}.")
        try:
            result = tool.run(self.context, given)
            payload = tool.output_model.model_validate(result.model_dump()).model_dump(mode="json")
        except Refused as refusal:
            return _plain(str(refusal))
        except ValidationError as error:
            return _plain(f"{name} produced a result that does not match its schema: {_problems(error)}.")
        except Exception as error:
            message = getattr(error, "message", None) or str(error)
            hint = getattr(error, "hint", None)
            return _plain(f"{message} {hint}" if hint else str(message))
        return {
            "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
            "structuredContent": payload,
            "isError": False,
        }

    def handle(self, message: Any) -> dict[str, Any] | None:
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or "method" not in message:
            return _error(
                message.get("id") if isinstance(message, dict) else None, INVALID_REQUEST, "Not a JSON-RPC 2.0 request."
            )
        identifier, method = message.get("id"), message["method"]
        params = message.get("params") or {}
        if "id" not in message:
            return None
        if method == "initialize":
            asked = params.get("protocolVersion")
            version = asked if asked in SUPPORTED_VERSIONS else SUPPORTED_VERSIONS[0]
            result: dict[str, Any] = {
                "protocolVersion": version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "verano", "version": __version__},
                "instructions": INSTRUCTIONS,
            }
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": [self.describe(tool) for tool in self.tools.values()]}
        elif method == "tools/call":
            if not isinstance(params.get("name"), str) or not isinstance(params.get("arguments", {}), dict):
                return _error(identifier, INVALID_PARAMS, "tools/call needs a tool name and an arguments object.")
            result = self.call(params["name"], params.get("arguments", {}))
        else:
            return _error(identifier, METHOD_NOT_FOUND, f"Unknown method {method}.")
        return {"jsonrpc": "2.0", "id": identifier, "result": result}

    def serve(self, source: TextIO, sink: TextIO, log: Callable[[str], None]) -> None:
        for line in source:
            if not line.strip():
                continue
            try:
                message = json.loads(line)
            except ValueError:
                reply: dict[str, Any] | None = _error(None, PARSE_ERROR, "That was not valid JSON.")
            else:
                reply = self.handle(message)
            if reply is not None:
                sink.write(json.dumps(reply, ensure_ascii=False) + "\n")
                sink.flush()
        log("Input closed; the Verano MCP server stopped.")
