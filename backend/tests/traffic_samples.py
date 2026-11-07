"""
Realistic sample exports for the traffic import tests, written by hand in the shape each tool produces:
OpenTelemetry GenAI (OTLP JSON), a browser HAR file, Langfuse, Phoenix and LangSmith. Each builder takes the question
and answer so tests can make many distinct traces; `*_sample()` returns a small mixed file with one bad record.
"""

import base64
import json
import time
from typing import Any

T0 = int(time.time()) - 7_200  # seconds, two hours ago, so spans fall on today; OTLP times are in nanoseconds


def _s(key: str, value: str) -> dict[str, Any]:
    return {"key": key, "value": {"stringValue": value}}


def _i(key: str, value: int) -> dict[str, Any]:
    return {"key": key, "value": {"intValue": str(value)}}


def otel_span(
    index: int, question: str, answer: str, *, error: bool = False, style: str = "messages"
) -> dict[str, Any]:
    start = (T0 + index) * 1_000_000_000
    attributes = [
        _s("gen_ai.system", "openai"),
        _s("gen_ai.request.model", "gpt-4o-mini"),
        _s("gen_ai.response.model", "gpt-4o-mini-2024-07-18"),
        _i("gen_ai.usage.input_tokens", 41),
        _i("gen_ai.usage.output_tokens", 17),
    ]
    events: list[dict[str, Any]] = []
    if style == "messages":
        attributes.append(_s("gen_ai.input.messages", json.dumps([{"role": "user", "content": question}])))
        attributes.append(_s("gen_ai.output.messages", json.dumps([{"role": "assistant", "content": answer}])))
    elif style == "indexed":
        attributes += [
            _s("gen_ai.prompt.0.role", "system"),
            _s("gen_ai.prompt.0.content", "You are a support agent."),
            _s("gen_ai.prompt.1.role", "user"),
            _s("gen_ai.prompt.1.content", question),
            _s("gen_ai.completion.0.role", "assistant"),
            _s("gen_ai.completion.0.content", answer),
        ]
    elif style == "events":
        events = [
            {"name": "gen_ai.user.message", "attributes": [_s("content", question)]},
            {"name": "gen_ai.choice", "attributes": [_s("message", json.dumps({"content": answer}))]},
        ]
    status = {"code": 2, "message": "rate limited"} if error else {"code": 1}
    return {
        "traceId": f"{index:032x}",
        "spanId": f"{index:016x}",
        "name": "chat gpt-4o-mini",
        "startTimeUnixNano": str(start),
        "endTimeUnixNano": str(start + 850_000_000),
        "attributes": attributes,
        "events": events,
        "status": status,
    }


def otel_export(spans: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "resourceSpans": [
            {
                "resource": {"attributes": [_s("service.name", "support-bot"), _s("deployment.environment", "prod")]},
                "scopeSpans": [{"scope": {"name": "opentelemetry.instrumentation.openai"}, "spans": spans}],
            }
        ]
    }


def database_span(index: int) -> dict[str, Any]:
    return {
        "traceId": f"{9000 + index:032x}",
        "spanId": f"{9000 + index:016x}",
        "name": "SELECT tickets",
        "startTimeUnixNano": str(T0 * 1_000_000_000),
        "endTimeUnixNano": str(T0 * 1_000_000_000 + 5),
        "attributes": [_s("db.system", "postgresql")],
    }


def otel_sample() -> dict[str, Any]:
    return otel_export(
        [
            otel_span(1, "Where is my order 4471?", "It ships tomorrow."),
            otel_span(2, "Reset my password", "Use the link on the sign-in page.", style="indexed"),
            otel_span(3, "Cancel my plan", "Done, it ends this month.", style="events"),
            otel_span(4, "Refund please", "", error=True),
            database_span(1),
            {  # a model call with no content captured: a problem, not a crash
                "traceId": f"{77:032x}",
                "spanId": f"{77:016x}",
                "name": "chat",
                "attributes": [_s("gen_ai.system", "openai")],
            },
        ]
    )


def har_entry(question: str, answer: str, *, status: int = 200, encoded: bool = False) -> dict[str, Any]:
    body = json.dumps({"answer": answer})
    content: dict[str, Any] = {"mimeType": "application/json", "text": body}
    if encoded:
        content = {
            "mimeType": "application/json",
            "encoding": "base64",
            "text": base64.b64encode(body.encode()).decode(),
        }
    return {
        "startedDateTime": "2025-11-03T09:15:00.000Z",
        "time": 412.5,
        "request": {
            "method": "POST",
            "url": "https://app.example.com/api/chat?session=s3cr3t",
            "headers": [
                {"name": "Authorization", "value": "Bearer sk-live-SUPERSECRET"},
                {"name": "Cookie", "value": "sid=abc123"},
            ],
            "postData": {
                "mimeType": "application/json",
                "text": json.dumps({"messages": [{"role": "user", "content": question}]}),
            },
        },
        "response": {"status": status, "headers": [{"name": "Set-Cookie", "value": "sid=zzz"}], "content": content},
    }


def har_sample() -> dict[str, Any]:
    return {
        "log": {
            "version": "1.2",
            "creator": {"name": "Chrome DevTools", "version": "1"},
            "entries": [
                har_entry("How do I export my data?", "Open Settings, then Export."),
                har_entry("What is the price?", "It is 20 a month.", encoded=True),
                har_entry("Break it", "Internal error", status=500),
                {"request": {"method": "GET", "url": "https://app.example.com/logo.png"}, "response": {"status": 200}},
                "not an entry",
            ],
        }
    }


def langfuse_trace(
    index: int, question: str, answer: str, *, error: bool = False, rating: float | None = None
) -> dict[str, Any]:
    trace: dict[str, Any] = {
        "id": f"lf-trace-{index}",
        "timestamp": "2025-11-02T10:00:00.000Z",
        "name": "support-chat",
        "input": {"question": question},
        "output": answer,
        "sessionId": f"sess-{index}",
        "tags": ["prod"],
        "latency": 1.25,
        "totalCost": 0.0004,
        "metadata": {"tenant": "acme"},
        "observations": [
            {
                "type": "GENERATION",
                "model": "gpt-4o-mini",
                "promptName": "triage",
                "promptVersion": 7,
                "usage": {"input": 30, "output": 12},
                "level": "ERROR" if error else "DEFAULT",
                "statusMessage": "context length exceeded" if error else None,
            }
        ],
        "scores": [],
    }
    if rating is not None:
        trace["scores"] = [{"name": "user-feedback", "value": rating}]
    return trace


def langfuse_sample() -> dict[str, Any]:
    return {
        "data": [
            langfuse_trace(1, "Do you ship to Canada?", "Yes, in 5 days.", rating=1),
            langfuse_trace(2, "My card was declined", "Try another card.", rating=0),
            langfuse_trace(3, "Broken call", "", error=True),
            {"id": "lf-empty", "observations": []},
            "garbage",
        ]
    }


def phoenix_span(
    trace: str, span: str, parent: str | None, kind: str, question: str, answer: str, *, error: bool = False
) -> dict[str, Any]:
    return {
        "name": "ChatCompletion" if kind == "LLM" else "agent.run",
        "span_kind": kind,
        "parent_id": parent,
        "start_time": "2025-11-04T12:00:00.000+00:00",
        "end_time": "2025-11-04T12:00:02.000+00:00",
        "status_code": "ERROR" if error else "OK",
        "status_message": "timeout" if error else "",
        "context": {"trace_id": trace, "span_id": span},
        "attributes": {
            "input": {"value": question},
            "output": {"value": answer},
            "llm": {"model_name": "gpt-4o", "token_count": {"prompt": 50, "completion": 20}},
            "session": {"id": "ph-sess"},
        },
    }


def phoenix_sample() -> dict[str, Any]:
    return {
        "spans": [
            phoenix_span("t1", "s1", None, "CHAIN", "Update my address", "Updated."),
            phoenix_span("t1", "s2", "s1", "LLM", "inner prompt", "inner answer"),
            phoenix_span("t2", "s3", None, "LLM", "Delete my account", "Please confirm by email.", error=True),
            {"span_kind": "LLM", "context": {"trace_id": "t3", "span_id": "s4"}, "attributes": {}},
        ]
    }


def langsmith_run(
    trace: str, run: str, parent: str | None, kind: str, question: str, answer: str, *, error: str | None = None
) -> dict[str, Any]:
    return {
        "id": run,
        "trace_id": trace,
        "parent_run_id": parent,
        "name": "support_chain" if kind == "chain" else "ChatOpenAI",
        "run_type": kind,
        "start_time": "2025-11-05T08:00:00.000000",
        "end_time": "2025-11-05T08:00:03.500000",
        "inputs": {"input": question},
        "outputs": {"output": answer} if answer else None,
        "error": error,
        "extra": {"metadata": {"ls_model_name": "gpt-4o-mini", "prompt_version": "v12"}},
        "prompt_tokens": 22,
        "completion_tokens": 9,
        "total_cost": 0.0002,
        "feedback_stats": {"user_score": {"n": 1, "avg": 0.0}},
        "tags": ["prod"],
    }


def langsmith_sample() -> dict[str, Any]:
    return {
        "runs": [
            langsmith_run("a", "a-root", None, "chain", "Change my email", "Changed."),
            langsmith_run("a", "a-llm", "a-root", "llm", "inner", "inner out"),
            langsmith_run("b", "b-root", None, "chain", "Broken chain", "", error="ValueError: boom"),
            {"id": "c", "trace_id": "c", "run_type": "chain", "inputs": {}, "outputs": {}},
        ]
    }


def as_bytes(data: Any) -> bytes:
    return json.dumps(data).encode()
