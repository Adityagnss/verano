"""
The response format of a run (ADR 0039): free text, a JSON object, or JSON that fits the task's output schema.

The choice is made once per run and sent to every model with the call, so the provider itself enforces it where it
can; the checks that read the answer afterwards (valid JSON, matches the schema) are unchanged and still run.
Pure: the service passes in the task's output schema.
"""

from typing import Any

from app.core.errors import ValidationFailed
from app.modules.engine.schemas import ResponseFormatKind

SCHEMA_NAME = "answer"
NO_SCHEMA = (
    "This task has no output schema, so there is no JSON schema to ask for. "
    "Add one in the Task Spec, or choose 'JSON object' or free text."
)


def resolve_format(kind: ResponseFormatKind, output_schema: dict[str, Any] | None) -> dict[str, Any] | None:
    """The `response_format` sent with each call, or None for free text."""
    if kind is ResponseFormatKind.TEXT:
        return None
    if kind is ResponseFormatKind.JSON_OBJECT:
        return {"type": "json_object"}
    if not output_schema:
        raise ValidationFailed(NO_SCHEMA)
    return {"type": "json_schema", "json_schema": {"name": SCHEMA_NAME, "schema": output_schema, "strict": False}}
