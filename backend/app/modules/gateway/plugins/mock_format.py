"""
How the mock provider honours a requested response format (ADR 0039), the way a real provider in JSON mode would:
a reply that is already valid JSON (and, for a schema, valid against it) is kept; any other reply is wrapped so the
result is valid. Pure and deterministic.
"""

import json
from typing import Any

import jsonschema

ANSWER_KEY = "answer"


def _value_for(schema: Any, text: str) -> Any:
    """A value that satisfies `schema`, using the reply for text."""
    if not isinstance(schema, dict):
        return text
    if schema.get("enum"):
        return schema["enum"][0]
    kind = schema.get("type")
    if isinstance(kind, list):
        kind = next((k for k in kind if k != "null"), "null")
    if kind == "object" or "properties" in schema:
        properties = schema.get("properties") or {}
        wanted = schema.get("required") or list(properties)
        return {name: _value_for(properties.get(name), text) for name in wanted}
    if kind == "array":
        return []
    if kind == "integer":
        return 0
    if kind == "number":
        return 0.0
    if kind == "boolean":
        return False
    if kind == "null":
        return None
    return text


def shape_reply(text: str, response_format: dict[str, Any] | None) -> str:
    """The reply as a model told to answer in `response_format` would give it."""
    kind = (response_format or {}).get("type")
    if kind not in ("json_object", "json_schema"):
        return text
    schema = ((response_format or {}).get("json_schema") or {}).get("schema") if kind == "json_schema" else None
    try:
        parsed = json.loads(text)
    except ValueError:
        parsed = None
    else:
        if kind == "json_object" and isinstance(parsed, dict):
            return text
        if kind == "json_schema" and schema and _valid(parsed, schema):
            return text
    if kind == "json_object" or not schema:
        return json.dumps({ANSWER_KEY: text}, ensure_ascii=False)
    return json.dumps(_value_for(schema, text), ensure_ascii=False)


def _valid(value: Any, schema: dict[str, Any]) -> bool:
    try:
        jsonschema.validate(value, schema)
    except (jsonschema.SchemaError, jsonschema.ValidationError):
        return False
    return True
