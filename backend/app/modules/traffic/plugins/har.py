"""
HAR file (HTTP Archive) of real calls to an app: what a browser or a proxy recorded.

Each entry is one call. The question is the request body (a chat-style message list, a JSON object with a
question-like field, or plain text), or the address' query text for a GET. The answer is the response body,
decoded from base64 when the file says so. Only the method, the address without its query string, the status and
the timing are kept as metadata: headers and cookies are never read, so keys and sessions in a HAR file are not stored.
An answer with a status of 400 or more is a failed call.
"""

import base64
import binascii
import json
from typing import Any, ClassVar
from urllib.parse import parse_qsl, urlsplit

from app.modules.traffic.domain import ParseResult, Problem, TraceRecord, input_text_of, output_text_of, parse_timestamp
from app.modules.traffic.plugins import adapter


def _entries(data: Any) -> list[Any]:
    log = data.get("log") if isinstance(data, dict) else None
    entries = log.get("entries") if isinstance(log, dict) else None
    return entries if isinstance(entries, list) else []


def _response_text(response: dict[str, Any]) -> str:
    content = response.get("content") or {}
    text = content.get("text")
    if not isinstance(text, str):
        return ""
    if content.get("encoding") == "base64":
        try:
            return base64.b64decode(text, validate=False).decode("utf-8", errors="replace")
        except (binascii.Error, ValueError):
            return ""
    return text


def _question(request: dict[str, Any]) -> str:
    post = request.get("postData") or {}
    text = post.get("text")
    if isinstance(text, str) and text.strip():
        try:
            return input_text_of(json.loads(text))
        except ValueError:
            return text
    params = post.get("params")
    if isinstance(params, list) and params:
        return input_text_of({str(p.get("name")): p.get("value") for p in params if isinstance(p, dict)})
    query = parse_qsl(urlsplit(str(request.get("url") or "")).query)
    return input_text_of(dict(query)) if query else ""


def _answer(response: dict[str, Any]) -> str:
    text = _response_text(response)
    if not text.strip():
        return ""
    try:
        return output_text_of(json.loads(text))
    except ValueError:
        return text


@adapter("har")
class HarAdapter:
    name: ClassVar[str] = "har"
    label: ClassVar[str] = "HAR file (calls to your app)"
    hint: ClassVar[str] = "Saved from your browser's network tab or a proxy: every call becomes one trace."

    def accepts(self, data: Any) -> bool:
        return isinstance(data, dict) and isinstance(data.get("log"), dict) and "entries" in data["log"]

    def parse(self, data: Any, limit: int) -> ParseResult:
        entries = _entries(data)
        result = ParseResult(found=len(entries))
        for number, entry in enumerate(entries[:limit], start=1):
            if not isinstance(entry, dict) or not isinstance(entry.get("request"), dict):
                result.problems.append(Problem(number, "This entry has no request in it, so it was skipped."))
                continue
            request, response = entry["request"], entry.get("response") or {}
            question, answer = _question(request), _answer(response if isinstance(response, dict) else {})
            if not question.strip() and not answer.strip():
                result.problems.append(
                    Problem(number, "This call has no request body and no reply text, so it was skipped.")
                )
                continue
            status = int(response.get("status") or 0) if isinstance(response, dict) else 0
            parts = urlsplit(str(request.get("url") or ""))
            failed = status >= 400
            time_ms = entry.get("time")
            result.records.append(
                TraceRecord(
                    external_id=None,
                    started_at=parse_timestamp(entry.get("startedDateTime")),
                    input_text=question,
                    output_text=answer,
                    status="error" if failed else "ok",
                    error_message=f"The app answered with status {status}." if failed else None,
                    latency_ms=round(float(time_ms)) if isinstance(time_ms, int | float) and time_ms >= 0 else None,
                    meta={
                        "method": str(request.get("method") or "")[:10],
                        "address": f"{parts.scheme}://{parts.netloc}{parts.path}" if parts.netloc else parts.path,
                        "status": status,
                    },
                )
            )
        return result
