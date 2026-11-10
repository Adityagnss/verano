"""
`verano.test(case, fn)` and `verano.serve(fn)`: test your own Python function, inside pytest or from Verano.

`test` calls your function with the case's input, turns what comes back (a string, a dict, a LangChain,
LlamaIndex or OpenAI result) into one `Reply`, checks it against what the case expects, and fails the pytest test
with a plain message when it does not match. Every call is recorded, so the pytest plugin can print a summary and
write a JSON report. `serve` wraps the same function in a tiny local web server, so Verano can run its whole test
set against your function through `verano app add` (the callable is then "your app" on the Run step).
Checks are deterministic (equals, contains, regex); judging with a model happens in Verano, not here.
"""

import json
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

ANSWER_KEYS = ("answer", "output", "text", "response", "result", "content")
CHUNK_KEYS = ("chunks", "source_documents", "context", "sources", "documents")
TOOL_KEYS = ("tool_calls", "tools")
MAX_BODY_BYTES = 1_000_000


@dataclass(frozen=True)
class Case:
    """One test case: what to send, and what the reply must satisfy. All checks given must hold."""

    input: Any
    expected: str | None = None
    contains: tuple[str, ...] = ()
    not_contains: tuple[str, ...] = ()
    regex: str | None = None
    name: str | None = None


@dataclass
class Reply:
    answer: str
    chunks: list[str] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Recorded:
    name: str
    passed: bool
    problems: list[str]
    answer: str


RECORDER: list[Recorded] = []


def _text_of(value: Any) -> str:
    if isinstance(value, str):
        return value
    for key in ("content", "page_content", "text", "response"):
        inner = value.get(key) if isinstance(value, dict) else getattr(value, key, None)
        if isinstance(inner, str):
            return inner
    return json.dumps(value, default=str, ensure_ascii=False)


def normalize(raw: Any) -> Reply:
    """A function's result as a Reply, whatever library it came from."""
    if isinstance(raw, Reply):
        return raw
    if isinstance(raw, dict):
        answer = next((raw[k] for k in ANSWER_KEYS if k in raw), None)
        chunks: list[Any] = next((raw[k] for k in CHUNK_KEYS if isinstance(raw.get(k), list)), [])
        tools: list[Any] = next((raw[k] for k in TOOL_KEYS if isinstance(raw.get(k), list)), [])
        return Reply(
            _text_of(answer if answer is not None else raw),
            [_text_of(c) for c in chunks],
            [t for t in tools if isinstance(t, dict)],
        )
    return Reply(_text_of(raw))


def problems_with(case: Case, reply: Reply) -> list[str]:
    """What is wrong with a reply, in plain words; empty when it satisfies the case."""
    answer = reply.answer
    found = []
    if case.expected is not None and " ".join(answer.split()).lower() != " ".join(case.expected.split()).lower():
        found.append(f"expected {case.expected!r} but the answer was {answer[:200]!r}")
    found += [f"the answer should contain {t!r}" for t in case.contains if t.lower() not in answer.lower()]
    found += [f"the answer should not contain {t!r}" for t in case.not_contains if t.lower() in answer.lower()]
    if case.regex is not None and not re.search(case.regex, answer):
        found.append(f"the answer does not match the pattern {case.regex!r}")
    return found


def test(case: Case, fn: Callable[[Any], Any]) -> Reply:
    """Run `fn` on the case; raise AssertionError when the reply does not satisfy it."""
    reply = normalize(fn(case.input))
    found = problems_with(case, reply)
    RECORDER.append(Recorded(case.name or str(case.input)[:60], not found, found, reply.answer))
    if found:
        raise AssertionError("Verano check failed: " + "; ".join(found) + ".")
    return reply


test.__test__ = False  # type: ignore[attr-defined]  # so pytest does not run `from verano.testing import test` as a test


class AppServer:
    """A local web server that answers Verano's app calls with your function: POST {"input": ...}."""

    def __init__(self, fn: Callable[[Any], Any], host: str = "127.0.0.1", port: int = 0) -> None:
        handler = _handler(fn)
        self._server = ThreadingHTTPServer((host, port), handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host!s}:{port}"

    def start(self) -> "AppServer":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def __enter__(self) -> "AppServer":
        return self.start()

    def __exit__(self, *_: object) -> None:
        self.stop()


def _handler(fn: Callable[[Any], Any]) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            size = int(self.headers.get("Content-Length") or 0)
            if size > MAX_BODY_BYTES:
                return self._send(413, {"error": "The request is too large."})
            try:
                given = json.loads(self.rfile.read(size) or b"{}")
                reply = normalize(fn(given.get("input") if isinstance(given, dict) else given))
            except Exception as error:
                return self._send(500, {"error": f"Your function failed: {error}"})
            return self._send(200, {"answer": reply.answer, "chunks": reply.chunks, "tool_calls": reply.tool_calls})

        def _send(self, status: int, body: dict[str, Any]) -> None:
            data = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format: str, *args: Any) -> None:
            return

    return Handler


def serve(fn: Callable[[Any], Any], host: str = "127.0.0.1", port: int = 0) -> AppServer:
    """`with verano.serve(fn) as server:` then register `server.url` with `verano app add`."""
    return AppServer(fn, host, port)
