"""
Phoenix export: spans as Arize Phoenix gives them (a list of records, or {"spans": [...]}), with the attributes
either nested ("attributes": {"input": {"value": ...}}) or flat ("attributes.input.value", as a dataframe export).

Spans are grouped by trace. A trace becomes one record: its top-level span when that has an input or an output,
otherwise its first model call (span kind LLM). Traces with neither are reported as problems.
"""

from typing import Any, ClassVar

from app.modules.traffic.domain import (
    ParseResult,
    Problem,
    TraceRecord,
    input_text_of,
    lookup,
    milliseconds_between,
    output_text_of,
    parse_timestamp,
    to_int,
)
from app.modules.traffic.plugins import adapter, records_of


def field(span: dict[str, Any], name: str) -> Any:
    """A value from a span by its dotted name, nested or flat, with or without the 'attributes.' start."""
    for candidate in (f"attributes.{name}", name):
        value = lookup(span, candidate)
        if value is not None:
            return value
    return None


def _trace_id(span: dict[str, Any]) -> str:
    return str(lookup(span, "context.trace_id") or span.get("trace_id") or "")


def _span_id(span: dict[str, Any]) -> str:
    return str(lookup(span, "context.span_id") or span.get("span_id") or "")


def _record(span: dict[str, Any]) -> TraceRecord | None:
    question = input_text_of(field(span, "input.value"))
    if not question.strip():
        question = input_text_of(field(span, "llm.input_messages"))
    answer = output_text_of(field(span, "output.value"))
    if not answer.strip():
        answer = output_text_of(field(span, "llm.output_messages"))
    if not question.strip() and not answer.strip():
        return None
    started, ended = parse_timestamp(span.get("start_time")), parse_timestamp(span.get("end_time"))
    status = str(span.get("status_code") or "").upper()
    failed = status == "ERROR"
    meta: dict[str, Any] = {"span_name": span.get("name"), "span_kind": span.get("span_kind")}
    session = field(span, "session.id")
    if session:
        meta["session_id"] = session
    trace_id, span_id = _trace_id(span), _span_id(span)
    return TraceRecord(
        external_id=f"{trace_id}:{span_id}" if trace_id and span_id else None,
        started_at=started,
        input_text=question,
        output_text=answer,
        status="error" if failed else "ok",
        error_message=str(span.get("status_message") or "") or None if failed else None,
        latency_ms=milliseconds_between(started, ended),
        model=str(field(span, "llm.model_name") or "") or None,
        prompt_version=str(field(span, "llm.prompt_template.version") or "") or None,
        tokens_in=to_int(field(span, "llm.token_count.prompt")),
        tokens_out=to_int(field(span, "llm.token_count.completion")),
        meta={key: value for key, value in meta.items() if value is not None},
    )


@adapter("phoenix")
class PhoenixAdapter:
    name: ClassVar[str] = "phoenix"
    label: ClassVar[str] = "Phoenix"
    hint: ClassVar[str] = "Spans exported from Arize Phoenix as JSON."

    def accepts(self, data: Any) -> bool:
        items = records_of(data, ("spans", "data"))
        sample = [item for item in items[:5] if isinstance(item, dict)]
        return bool(sample) and all(
            ("span_kind" in item or "context.span_id" in item or isinstance(item.get("context"), dict))
            and "run_type" not in item
            for item in sample
        )

    def parse(self, data: Any, limit: int) -> ParseResult:
        items = records_of(data, ("spans", "data"))
        result = ParseResult(found=len(items))
        traces: dict[str, list[tuple[int, dict[str, Any]]]] = {}
        for number, span in enumerate(items[:limit], start=1):
            if not isinstance(span, dict):
                result.problems.append(Problem(number, "This record is not a Phoenix span, so it was skipped."))
                continue
            traces.setdefault(_trace_id(span) or f"span-{number}", []).append((number, span))
        for spans in traces.values():
            roots = [pair for pair in spans if not (pair[1].get("parent_id") or lookup(pair[1], "context.parent_id"))]
            llms = [pair for pair in spans if str(pair[1].get("span_kind", "")).upper() == "LLM"]
            chosen: tuple[int, TraceRecord] | None = None
            for number, span in [*roots, *llms]:
                record = _record(span)
                if record is not None:
                    chosen = (number, record)
                    break
            if chosen is None:
                result.problems.append(
                    Problem(spans[0][0], "This trace has no input and no output on any model call, so it was skipped.")
                )
            else:
                result.records.append(chosen[1])
        return result
