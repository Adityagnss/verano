"""
Request and response mapping for connected apps (pure code, no I/O).

Request bodies are Jinja templates rendered in the shared sandbox with a `tojson` filter,
so any text becomes a valid JSON value. Responses are read with a small JSONPath subset
(`$`, `.key`, `['key']`, `[0]`, `[-1]`, `[*]`); it is parsed by hand and never evaluates
code, and recursive descent (`..`) is refused. `apply_mapping` turns a parsed response
body into an `AppReply` for the evaluators. Called by the apps service after each call.
"""

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Final

from jinja2 import TemplateSyntaxError, UndefinedError

from app.core.templates import sandboxed_environment

CHUNK_TEXT_KEYS: Final[tuple[str, ...]] = ("text", "content", "chunk", "page_content")
BRACKET_PATTERN: Final[re.Pattern[str]] = re.compile(r"\[(\*|-?\d+|'[^']*'|\"[^\"]*\")\]")
KEY_PATTERN: Final[re.Pattern[str]] = re.compile(r"\.([A-Za-z_][\w\-]*)")


class MappingError(ValueError):
    pass


class _Wildcard:
    pass


WILDCARD: Final = _Wildcard()
Step = str | int | _Wildcard


@dataclass(frozen=True)
class CompiledPath:
    path: str
    steps: tuple[Step, ...]


@dataclass(frozen=True)
class ResponseMapping:
    answer_path: str
    chunks_path: str | None
    tool_calls_path: str | None
    cost_path: str | None


@dataclass(frozen=True)
class AppReply:
    answer: str
    chunks: list[str]
    tool_calls: list[dict[str, Any]]
    cost: float | None


def _bracket_step(token: str) -> Step:
    if token == "*":
        return WILDCARD
    if token[0] in "'\"":
        return token[1:-1]
    return int(token)


@lru_cache(maxsize=256)
def compile_path(path: str) -> CompiledPath:
    if ".." in path:
        raise MappingError(f"Recursive search ('..') is not supported in {path}. Use an exact path like $.a.b[0].")
    if not path.startswith("$"):
        raise MappingError(f"The path {path} must start with $.")
    steps: list[Step] = []
    position = 1
    while position < len(path):
        match = KEY_PATTERN.match(path, position) or BRACKET_PATTERN.match(path, position)
        if match is None:
            raise MappingError(f"The path {path} is not valid at position {position}.")
        token = match.group(1)
        steps.append(token if path[position] == "." else _bracket_step(token))
        position = match.end()
    return CompiledPath(path, tuple(steps))


def _advance(node: Any, step: Step) -> list[Any]:
    if isinstance(step, _Wildcard):
        if isinstance(node, list):
            return list(node)
        return list(node.values()) if isinstance(node, dict) else []
    if isinstance(step, str):
        return [node[step]] if isinstance(node, dict) and step in node else []
    if isinstance(node, list) and -len(node) <= step < len(node):
        return [node[step]]
    return []


def extract(compiled: CompiledPath, data: Any) -> list[Any]:
    nodes = [data]
    for step in compiled.steps:
        nodes = [child for node in nodes for child in _advance(node, step)]
    return nodes


def first_or_error(path: str, data: Any) -> Any:
    matches = extract(compile_path(path), data)
    if not matches:
        raise MappingError(f"Nothing found at {path}.")
    return matches[0]


def render_request(template: str, inputs: dict[str, Any]) -> str:
    environment = sandboxed_environment()
    environment.filters["tojson"] = lambda value: json.dumps(value, ensure_ascii=False)
    try:
        return environment.from_string(template).render(**inputs)
    except TemplateSyntaxError as error:
        raise MappingError(f"The request template is not valid (line {error.lineno}): {error.message}") from error
    except UndefinedError as error:
        raise MappingError(f"The request template uses a variable that has no value: {error.message}") from error


def _as_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False) if isinstance(value, dict | list) else str(value)


def _chunk_text(item: Any) -> str:
    if isinstance(item, dict):
        key = next((name for name in CHUNK_TEXT_KEYS if name in item), None)
        return _as_text(item[key]) if key is not None else _as_text(item)
    return _as_text(item)


def _matches_as_list(path: str, body: Any) -> list[Any]:
    matches = extract(compile_path(path), body)
    if len(matches) == 1 and isinstance(matches[0], list):
        return matches[0]
    return matches


def _normalise_tool_call(item: Any) -> dict[str, Any]:
    call = item.get("function", item) if isinstance(item, dict) else None
    if not isinstance(call, dict) or not isinstance(call.get("name"), str):
        raise MappingError(f"A tool call must have a name, got {_as_text(item)}.")
    arguments = call.get("arguments", {})
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments) if arguments.strip() else {}
        except json.JSONDecodeError as error:
            raise MappingError(f"The arguments of tool call {call['name']} are not valid JSON.") from error
    if not isinstance(arguments, dict):
        raise MappingError(f"The arguments of tool call {call['name']} must be an object.")
    return {"name": call["name"], "arguments": arguments}


def _cost(path: str | None, body: Any) -> float | None:
    if path is None:
        return None
    matches = extract(compile_path(path), body)
    value = matches[0] if matches else None
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def apply_mapping(mapping: ResponseMapping, body: Any) -> AppReply:
    answer = _as_text(first_or_error(mapping.answer_path, body))
    chunks = [_chunk_text(item) for item in _matches_as_list(mapping.chunks_path, body)] if mapping.chunks_path else []
    raw_calls = _matches_as_list(mapping.tool_calls_path, body) if mapping.tool_calls_path else []
    return AppReply(
        answer=answer,
        chunks=chunks,
        tool_calls=[_normalise_tool_call(item) for item in raw_calls],
        cost=_cost(mapping.cost_path, body),
    )
