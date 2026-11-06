"""
OpenTelemetry GenAI (OTLP JSON), for a file of exported traces and for the live receiver.

A span is a model call when it carries GenAI attributes or events (`gen_ai.*`), or the OpenInference and
OpenLLMetry names for the same things (`input.value`, `llm.*`, `traceloop.*`). The prompt and the answer are read
from whichever form the instrumentation used: JSON message lists, indexed attributes (`gen_ai.prompt.0.content`),
events (`gen_ai.user.message`, `gen_ai.choice`) or plain input and output values. Other spans (a database call, a
web request) are counted as ignored, not as problems.
"""

from typing import Any, ClassVar

from app.modules.traffic.domain import (
    ParseResult,
    Problem,
    TraceRecord,
    input_text_of,
    milliseconds_between,
    normalize_rating,
    output_text_of,
    parse_timestamp,
    to_float,
    to_int,
)
from app.modules.traffic.plugins import adapter

SpanRow = tuple[dict[str, Any], dict[str, Any]]  # (resource attributes, span)
INPUT_EVENTS = ("gen_ai.user.message", "gen_ai.content.prompt", "gen_ai.system.message")
OUTPUT_EVENTS = ("gen_ai.choice", "gen_ai.content.completion", "gen_ai.assistant.message")
CONTENT_PREFIXES = ("gen_ai.prompt", "gen_ai.completion", "llm.input_messages", "llm.output_messages")
CONTENT_KEYS = frozenset(
    {
        "gen_ai.input.messages",
        "gen_ai.output.messages",
        "gen_ai.system_instructions",
        "input.value",
        "output.value",
        "traceloop.entity.input",
        "traceloop.entity.output",
    }
)


def any_value(value: Any) -> Any:
    """One OTLP JSON `AnyValue` as a plain Python value."""
    if not isinstance(value, dict):
        return value
    for key in ("stringValue", "boolValue", "doubleValue"):
        if key in value:
            return value[key]
    if "intValue" in value:
        number = to_int(value["intValue"])
        return number if number is not None else value["intValue"]
    if "arrayValue" in value:
        return [any_value(item) for item in (value["arrayValue"] or {}).get("values", [])]
    if "kvlistValue" in value:
        return attributes((value["kvlistValue"] or {}).get("values", []))
    return None


def attributes(items: Any) -> dict[str, Any]:
    """OTLP JSON attributes (a list of {"key", "value"}) as a dictionary."""
    out: dict[str, Any] = {}
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict) and "key" in item:
                out[str(item["key"])] = any_value(item.get("value"))
    return out


def looks_like_otlp(data: Any) -> bool:
    parts = data if isinstance(data, list) else [data]
    return any(isinstance(part, dict) and ("resourceSpans" in part or "resource_spans" in part) for part in parts)


def flatten_spans(payload: Any) -> list[SpanRow]:
    """Every span of a request or file with the attributes of the resource that sent it."""
    rows: list[SpanRow] = []
    for part in payload if isinstance(payload, list) else [payload]:
        if not isinstance(part, dict):
            continue
        for batch in part.get("resourceSpans") or part.get("resource_spans") or []:
            if not isinstance(batch, dict):
                continue
            resource = attributes((batch.get("resource") or {}).get("attributes"))
            scopes = batch.get("scopeSpans") or batch.get("scope_spans") or batch.get("instrumentationLibrarySpans")
            for scope in scopes or []:
                for span in (scope or {}).get("spans") or []:
                    if isinstance(span, dict):
                        rows.append((resource, span))
    return rows


def _indexed(attrs: dict[str, Any], prefix: str) -> list[dict[str, Any]]:
    """Messages stored one attribute each: `<prefix>.0.role`, `<prefix>.0.content`, ... in order."""
    found: dict[int, dict[str, Any]] = {}
    for key, value in attrs.items():
        if not key.startswith(prefix + "."):
            continue
        parts = key[len(prefix) + 1 :].split(".")
        if not parts[0].isdigit():
            continue
        slot = found.setdefault(int(parts[0]), {})
        name = ".".join(part for part in parts[1:] if part != "message")
        slot[name or "content"] = value
    return [found[i] for i in sorted(found)]


def _event_text(events: list[dict[str, Any]], names: tuple[str, ...], reader: Any) -> str:
    texts = []
    for event in events:
        if event.get("name") in names:
            data = attributes(event.get("attributes"))
            body = (
                data.get("content") or data.get("message") or data.get("gen_ai.prompt") or data.get("gen_ai.completion")
            )
            if body is None:
                body = {key: value for key, value in data.items() if key != "gen_ai.system"}
            text = reader(body)
            if text:
                texts.append(text)
    return texts[-1] if texts else ""


def span_input(attrs: dict[str, Any], events: list[dict[str, Any]]) -> str:
    for key in ("gen_ai.input.messages", "gen_ai.prompt", "input.value", "traceloop.entity.input"):
        if attrs.get(key) not in (None, ""):
            return input_text_of(attrs[key])
    for prefix in ("gen_ai.prompt", "llm.input_messages"):
        messages = _indexed(attrs, prefix)
        if messages:
            return input_text_of(messages)
    return _event_text(events, INPUT_EVENTS, input_text_of)


def span_output(attrs: dict[str, Any], events: list[dict[str, Any]]) -> str:
    for key in ("gen_ai.output.messages", "gen_ai.completion", "output.value", "traceloop.entity.output"):
        if attrs.get(key) not in (None, ""):
            return output_text_of(attrs[key])
    for prefix in ("gen_ai.completion", "llm.output_messages"):
        messages = _indexed(attrs, prefix)
        if messages:
            return output_text_of(messages)
    return _event_text(events, OUTPUT_EVENTS, output_text_of)


def is_model_call(attrs: dict[str, Any], events: list[dict[str, Any]]) -> bool:
    if any(key.startswith(("gen_ai.", "llm.", "traceloop.")) for key in attrs) or "input.value" in attrs:
        return True
    return any(str(event.get("name", "")).startswith("gen_ai.") for event in events)


def _first(attrs: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if attrs.get(key) not in (None, ""):
            return attrs[key]
    return None


def parse_span(resource: dict[str, Any], span: dict[str, Any]) -> TraceRecord | None:
    """One span as a trace, or None when it is not a model call."""
    attrs = attributes(span.get("attributes"))
    events = [event for event in span.get("events") or [] if isinstance(event, dict)]
    if not is_model_call(attrs, events):
        return None
    started = parse_timestamp(span.get("startTimeUnixNano"))
    ended = parse_timestamp(span.get("endTimeUnixNano"))
    status = span.get("status") or {}
    failed = status.get("code") in (2, "2", "STATUS_CODE_ERROR") or "error.type" in attrs
    message = status.get("message") or attrs.get("error.type") or attrs.get("exception.message")
    meta: dict[str, Any] = {
        key: value
        for key, value in attrs.items()
        if key not in CONTENT_KEYS and not key.startswith(CONTENT_PREFIXES) and not isinstance(value, dict | list)
    }
    if span.get("name"):
        meta["span_name"] = span["name"]
    for key in ("service.name", "service.version", "deployment.environment"):
        if resource.get(key) is not None:
            meta[key] = resource[key]
    trace_id, span_id = span.get("traceId"), span.get("spanId")
    return TraceRecord(
        external_id=f"{trace_id}:{span_id}" if trace_id and span_id else None,
        started_at=started,
        input_text=span_input(attrs, events),
        output_text=span_output(attrs, events),
        status="error" if failed else "ok",
        error_message=str(message) if failed and message else None,
        latency_ms=milliseconds_between(started, ended),
        model=str(_first(attrs, "gen_ai.response.model", "gen_ai.request.model", "llm.model_name") or "") or None,
        prompt_version=str(_first(attrs, "verano.prompt_version", "gen_ai.prompt.version") or "") or None,
        rating=normalize_rating(_first(attrs, "verano.rating", "user.feedback", "feedback.score")),
        tokens_in=to_int(
            _first(attrs, "gen_ai.usage.input_tokens", "gen_ai.usage.prompt_tokens", "llm.token_count.prompt")
        ),
        tokens_out=to_int(
            _first(attrs, "gen_ai.usage.output_tokens", "gen_ai.usage.completion_tokens", "llm.token_count.completion")
        ),
        cost=to_float(_first(attrs, "gen_ai.usage.cost", "llm.cost.total")),
        meta=meta,
    )


NO_CONTENT = (
    "This model call has neither a prompt nor an answer in it. Turn on content capture in the instrumentation "
    "(for example OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true)."
)


def parse_spans(rows: list[SpanRow]) -> ParseResult:
    result = ParseResult(found=len(rows))
    for number, (resource, span) in enumerate(rows, start=1):
        record = parse_span(resource, span)
        if record is None:
            result.ignored += 1
        elif not record.input_text.strip() and not record.output_text.strip():
            result.problems.append(Problem(number, NO_CONTENT))
        else:
            result.records.append(record)
    return result


@adapter("otel")
class OpenTelemetryAdapter:
    name: ClassVar[str] = "otel"
    label: ClassVar[str] = "OpenTelemetry (GenAI)"
    hint: ClassVar[str] = "A JSON file of OTLP traces (one export, or one export per line)."

    def accepts(self, data: Any) -> bool:
        return looks_like_otlp(data)

    def parse(self, data: Any, limit: int) -> ParseResult:
        return parse_spans(flatten_spans(data)[:limit])
