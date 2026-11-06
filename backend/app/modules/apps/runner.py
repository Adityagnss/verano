"""
Calling the user's app (ADR 0024, ADR 0025, ADR 0026).

One call renders the request template with the case's inputs, sends it through the guarded client (which refuses
internal addresses unless the owner allowed the host, validates every redirect, caps the reply and the time), and
reads the answer, retrieved chunks, tool calls and cost out of the JSON reply with the target's mapping. A failure
is returned as text that says what to do, never raised, so one bad call cannot stop a run. Transient failures are
retried only as many times as the target allows (none by default). Secrets are never part of what is recorded.
"""

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import Settings
from app.core.egress import EgressPolicy, guarded_request
from app.core.errors import AppError
from app.modules.apps.mapping import AppReply, MappingError, ResponseMapping, apply_mapping, render_request

NOT_JSON = "The app's reply is not JSON, so Verano cannot find the answer in it."
HTTP_FAILED = "The app answered with status {status}."
RETRY_BACKOFF_S = 0.5
TRANSIENT = frozenset({429, 500, 502, 503, 504})


@dataclass(frozen=True)
class AppSpec:
    """What a call needs from a stored target; kept apart from the table so the runner is easy to use and test."""

    url: str
    method: str
    request_template: str
    mapping: ResponseMapping
    timeout_s: float
    retries: int


@dataclass
class AppCallResult:
    request_body: str
    status_code: int | None = None
    response_body: str | None = None
    truncated: bool = False
    latency_ms: int | None = None
    reply: AppReply | None = None
    error: str | None = None


class AppRunner:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._settings = settings
        self._transport = transport

    def policy(self, timeout_s: float) -> EgressPolicy:
        settings = self._settings
        return EgressPolicy(
            allowed_hosts=frozenset(host.lower() for host in settings.app_allowed_hosts),
            max_bytes=settings.app_response_max_bytes,
            timeout_s=timeout_s,
            max_redirects=settings.app_max_redirects,
        )

    async def call(self, spec: AppSpec, headers: dict[str, str], inputs: dict[str, Any]) -> AppCallResult:
        try:
            body = render_request(spec.request_template, inputs)
        except MappingError as exc:
            return AppCallResult(request_body="", error=str(exc))
        result = AppCallResult(request_body=body)
        for attempt in range(spec.retries + 1):
            result = await self._once(spec, headers, body)
            if result.error is None or attempt == spec.retries or not self._retryable(result):
                return result
            await asyncio.sleep(RETRY_BACKOFF_S * (attempt + 1))
        return result

    @staticmethod
    def _retryable(result: AppCallResult) -> bool:
        return result.status_code is None or result.status_code in TRANSIENT

    async def _once(self, spec: AppSpec, headers: dict[str, str], body: str) -> AppCallResult:
        sent = {"Content-Type": "application/json", "Accept": "application/json", **headers}
        started = time.monotonic()
        try:
            response = await guarded_request(
                spec.method,
                spec.url,
                headers=sent,
                body=body.encode() if spec.method != "GET" else None,
                policy=self.policy(spec.timeout_s),
                transport=self._transport,
            )
        except AppError as exc:
            return AppCallResult(request_body=body, error=exc.message, latency_ms=_elapsed(started))
        text = response.body.decode("utf-8", errors="replace")
        result = AppCallResult(
            request_body=body,
            status_code=response.status,
            response_body=text,
            truncated=response.truncated,
            latency_ms=round(response.elapsed_ms),
        )
        if response.status >= 400:
            result.error = HTTP_FAILED.format(status=response.status)
            return result
        try:
            data = json.loads(text)
        except ValueError:
            result.error = NOT_JSON
            return result
        try:
            result.reply = apply_mapping(spec.mapping, data)
        except MappingError as exc:
            result.error = str(exc)
        return result


def _elapsed(started: float) -> int:
    return round((time.monotonic() - started) * 1000)
