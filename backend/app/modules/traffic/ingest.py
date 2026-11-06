"""
Getting traces in: a file import and the live OTLP receiver (ADR 0031).

Both end the same way: every record is cut to its size caps, cleaned of personal data (on by default, before anything
is stored) and written in batches; a record already stored is skipped. A file is read into memory once, within a
size cap, and parsed in a worker thread so the API stays responsive. The receiver accepts OTLP/HTTP with JSON bodies,
checks the project's ingest token, and under load drops extra spans instead of falling behind: the drop is counted
per day and shown. Parsing is pure (the adapters and `domain.py`); this file only wires it to the database.
"""

import asyncio
import hashlib
import json
import time
import uuid
import zlib
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.container import Container
from app.core.errors import AppError, AuthenticationFailed, ValidationFailed
from app.core.ids import uuid7
from app.core.registry import load_plugins
from app.core.security import digest_token, utcnow
from app.modules.traffic import plugins as plugin_package
from app.modules.traffic.config import effective_config, scrub_of
from app.modules.traffic.domain import (
    ParseResult,
    ScrubConfig,
    TraceRecord,
    bound_meta,
    clip,
    scrub_text,
    scrub_value,
    topic_hash,
)
from app.modules.traffic.models import TrafficToken
from app.modules.traffic.plugins import ADAPTERS, ImportAdapter
from app.modules.traffic.plugins.otel import flatten_spans, parse_spans
from app.modules.traffic.repository import TrafficRepository
from app.modules.traffic.schemas import ImportReport, ProblemOut

TOKEN_PREFIX = "vti_"
AUTO = "auto"
DETECTION_ORDER = ("otel", "har", "langsmith", "phoenix", "langfuse")
PROCESS_JOB = "traffic.process"
PURGE_JOB = "traffic.purge"
TOUCH_EVERY_S = 300
ERROR_CHARS = 1_000
FILE_TOO_LARGE = (
    "This file is larger than {limit} MB, the most Verano reads in one import. Split it and import the parts."
)
NOT_JSON = "This file is not valid JSON (it stops making sense near line {line}). Export it again as JSON."
UNKNOWN_FORMAT = (
    "Verano could not tell which tool this file came from. It reads: {formats}. Choose the format yourself."
)
NOTHING_FOUND = "No {label} traces were found in this file. Check that you chose the right format."
EMPTY_FILE = "This file is empty."
BAD_TOKEN = "This ingest token is not valid or was revoked. Create a new one under Traffic, then Ingest tokens."
NOT_JSON_BODY = "Send the spans as JSON: set OTEL_EXPORTER_OTLP_PROTOCOL=http/json (protobuf is not supported)."
TOO_LARGE_BODY = "This request is larger than {limit} MB, so it was dropped. Send smaller batches."
BAD_BODY = "The body is not valid OTLP JSON, so nothing was stored."
OVER_RATE = "Over the limit of {limit} spans a minute for this project: {count} spans were dropped."
OVER_SIZE = "A request can carry at most {limit} spans: {count} were dropped."


class PayloadTooLarge(AppError):
    status_code = 413
    code = "payload_too_large"


class UnsupportedMedia(AppError):
    status_code = 415
    code = "unsupported_media_type"


def adapters() -> dict[str, ImportAdapter]:
    load_plugins(plugin_package.__name__)
    return dict(ADAPTERS.items())


def format_choices() -> list[tuple[str, str, str]]:
    found = adapters()
    return [(name, found[name].label, found[name].hint) for name in sorted(found)]


# ----------------------------------------------------------------------------------------------- one record


def external_id_of(source: str, record: TraceRecord) -> str:
    """The record's own id, or (for files that have none, like a HAR) a fingerprint of its content, so importing the
    same file twice stores each trace once."""
    if record.external_id:
        return record.external_id[:200]
    stamp = record.started_at.isoformat() if record.started_at else ""
    digest = hashlib.blake2b(
        f"{source}|{stamp}|{record.input_text}|{record.output_text}".encode(), digest_size=16
    ).hexdigest()
    return f"h:{digest}"


@dataclass
class BuiltRow:
    values: dict[str, Any]
    scrubbed: int
    truncated: bool


def build_row(
    record: TraceRecord,
    *,
    project_id: uuid.UUID,
    source: str,
    scrub: ScrubConfig,
    settings: Settings,
    now: datetime,
    prompt_version: str | None = None,
) -> BuiltRow:
    """One storable row: every text cut to its cap (and flagged), then cleaned of personal data. Cutting comes first
    so the cleaning work is bounded however large a record is."""
    limit = settings.traffic_field_max_chars
    question, question_cut = clip(record.input_text, limit)
    answer, answer_cut = clip(record.output_text, limit)
    error, _ = clip(record.error_message or "", ERROR_CHARS)
    question, found_in = scrub_text(question, scrub)
    answer, found_out = scrub_text(answer, scrub)
    error, found_error = scrub_text(error, scrub)
    meta, found_meta = scrub_value(record.meta, scrub)
    meta, meta_cut = bound_meta(meta, settings.traffic_meta_max_chars)
    values: dict[str, Any] = {
        "id": uuid7(),
        "project_id": project_id,
        "source": source,
        "external_id": external_id_of(source, record),
        "started_at": record.started_at or now,
        "input_text": question,
        "output_text": answer,
        "input_truncated": question_cut,
        "output_truncated": answer_cut,
        "status": record.status if record.status in ("ok", "error") else "ok",
        "error_message": error or None,
        "latency_ms": record.latency_ms,
        "model": record.model[:200] if record.model else None,
        "prompt_version": (record.prompt_version or prompt_version or "")[:100] or None,
        "rating": record.rating,
        "tokens_in": record.tokens_in,
        "tokens_out": record.tokens_out,
        "cost": record.cost,
        "meta": meta,
        "scrubbed_count": found_in + found_out + found_error + found_meta,
        "topic_hash": topic_hash(question),
        "score_state": "new",
    }
    return BuiltRow(values, values["scrubbed_count"], question_cut or answer_cut or meta_cut)


# ----------------------------------------------------------------------------------------------- reading files


def load_json(raw: bytes) -> Any:
    """The JSON in a file, or in a file of one JSON value per line (JSON Lines)."""
    text = raw.decode("utf-8-sig", errors="replace").strip()
    if not text:
        raise ValidationFailed(EMPTY_FILE)
    try:
        return json.loads(text)
    except ValueError as whole:
        lines = [line for line in text.splitlines() if line.strip()]
        values = []
        for number, line in enumerate(lines, start=1):
            try:
                values.append(json.loads(line))
            except ValueError:
                line_number = getattr(whole, "lineno", number)
                raise ValidationFailed(NOT_JSON.format(line=line_number)) from None
        return values


def choose_adapter(data: Any, requested: str) -> ImportAdapter:
    found = adapters()
    if requested != AUTO:
        return found[requested]
    for name in DETECTION_ORDER:
        if name in found and found[name].accepts(data):
            return found[name]
    raise ValidationFailed(UNKNOWN_FORMAT.format(formats=", ".join(found[name].label for name in sorted(found))))


@dataclass
class Prepared:
    adapter: ImportAdapter
    parsed: ParseResult
    rows: list[dict[str, Any]]
    scrubbed: int
    truncated: int


def prepare_import(
    raw: bytes,
    requested: str,
    *,
    project_id: uuid.UUID,
    scrub: ScrubConfig,
    settings: Settings,
    now: datetime,
    prompt_version: str | None,
) -> Prepared:
    """Everything about an import that needs no database: read, recognise, parse, cut and clean. Runs in a thread."""
    data = load_json(raw)
    adapter = choose_adapter(data, requested)
    parsed = adapter.parse(data, settings.traffic_import_max_records)
    if parsed.found == 0:
        raise ValidationFailed(NOTHING_FOUND.format(label=adapter.label))
    built = [
        build_row(
            record,
            project_id=project_id,
            source=adapter.name,
            scrub=scrub,
            settings=settings,
            now=now,
            prompt_version=prompt_version,
        )
        for record in parsed.records
    ]
    return Prepared(
        adapter=adapter,
        parsed=parsed,
        rows=[item.values for item in built],
        scrubbed=sum(item.scrubbed for item in built),
        truncated=sum(item.truncated for item in built),
    )


async def read_limited(chunks: AsyncIterator[bytes], limit: int) -> bytes | None:
    """The bytes of a stream, or None as soon as it is longer than `limit`."""
    parts: list[bytes] = []
    size = 0
    async for chunk in chunks:
        size += len(chunk)
        if size > limit:
            return None
        parts.append(chunk)
    return b"".join(parts)


def gunzip_limited(body: bytes, limit: int) -> bytes | None:
    """A gzip body unpacked, or None when it unpacks to more than `limit` bytes (a decompression bomb)."""
    unpacker = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        data = unpacker.decompress(body, limit + 1)
    except zlib.error as error:
        raise ValidationFailed(BAD_BODY) from error
    return None if len(data) > limit or unpacker.unconsumed_tail else data


class ImportService:
    def __init__(self, session: AsyncSession, container: Container) -> None:
        self._session = session
        self._settings = container.settings
        self._repo = TrafficRepository(session)

    async def import_file(
        self, project_id: uuid.UUID, raw: bytes | None, format_name: str, prompt_version: str | None
    ) -> ImportReport:
        settings = self._settings
        if raw is None:
            raise ValidationFailed(FILE_TOO_LARGE.format(limit=settings.traffic_import_max_bytes // 1_000_000))
        if format_name != AUTO and format_name not in adapters():
            raise ValidationFailed(f"Verano does not read the format '{format_name}'.")
        config = effective_config(await self._repo.config(project_id), settings)
        prepared = await asyncio.to_thread(
            prepare_import,
            raw,
            format_name,
            project_id=project_id,
            scrub=scrub_of(config),
            settings=settings,
            now=utcnow(),
            prompt_version=(prompt_version or "").strip() or None,
        )
        stored = await self._repo.insert_traces(prepared.rows)
        await self._repo.add_ingest_counts(
            project_id, utcnow().date(), accepted=stored, ignored=prepared.parsed.ignored
        )
        limit = settings.traffic_problem_limit
        problems = prepared.parsed.problems
        return ImportReport(
            format=prepared.adapter.name,
            format_label=prepared.adapter.label,
            found=prepared.parsed.found,
            imported=stored,
            duplicates=len(prepared.rows) - stored,
            ignored=prepared.parsed.ignored,
            truncated=prepared.truncated,
            scrubbed=prepared.scrubbed,
            problems=[ProblemOut(record=p.record, message=p.message) for p in problems[:limit]],
            more_problems=max(0, len(problems) - limit),
        )


# ----------------------------------------------------------------------------------------------- the receiver


class SpanBudget:
    """How many spans a project may send in the current minute, counted across every API process on Valkey."""

    def __init__(self, valkey: Redis, per_minute: int) -> None:
        self._valkey = valkey
        self._per_minute = per_minute

    async def take(self, project_id: uuid.UUID, wanted: int, now: float | None = None) -> int:
        """Counts `wanted` spans against this minute and returns how many of them fit."""
        if wanted <= 0:
            return 0
        window = int((now if now is not None else time.time()) // 60)
        key = f"traffic:spans:{project_id}:{window}"
        pipe = self._valkey.pipeline(transaction=True)
        pipe.incrby(key, wanted)
        pipe.expire(key, 120, nx=True)
        count, _ = await pipe.execute()
        before = int(count) - wanted
        return max(0, min(wanted, self._per_minute - before))


@dataclass
class ReceiveResult:
    accepted: int
    dropped: int
    message: str | None

    def body(self) -> dict[str, Any]:
        if not self.dropped:
            return {}
        return {"partialSuccess": {"rejectedSpans": self.dropped, "errorMessage": self.message or ""}}


class ReceiverService:
    def __init__(self, session: AsyncSession, container: Container) -> None:
        self._session = session
        self._container = container
        self._settings = container.settings
        self._repo = TrafficRepository(session)
        self._budget = SpanBudget(container.valkey, container.settings.traffic_spans_per_minute)

    async def authenticate(self, raw_token: str | None) -> TrafficToken:
        if not raw_token or not raw_token.startswith(TOKEN_PREFIX):
            raise AuthenticationFailed(BAD_TOKEN)
        token = await self._repo.token_by_hash(digest_token(raw_token))
        if token is None:
            raise AuthenticationFailed(BAD_TOKEN)
        from datetime import timedelta

        await self._repo.touch_token(token.id, utcnow(), timedelta(seconds=TOUCH_EVERY_S))
        return token

    async def reject_oversized(self, project_id: uuid.UUID) -> None:
        """Counts a request that was too large to read, so the drop shows on the Traffic screen. The caller commits
        before raising, because a raised error rolls the request's session back."""
        await self._repo.add_ingest_counts(project_id, utcnow().date(), rejected_requests=1)

    async def receive(self, token: TrafficToken, body: bytes, prompt_version: str | None = None) -> ReceiveResult:
        settings = self._settings
        project_id = token.project_id
        try:
            payload = await asyncio.to_thread(json.loads, body) if len(body) > 200_000 else json.loads(body)
        except ValueError as error:
            raise ValidationFailed(BAD_BODY) from error
        spans = flatten_spans(payload)
        today = utcnow().date()
        messages: list[str] = []
        over_size = max(0, len(spans) - settings.traffic_receiver_max_spans)
        if over_size:
            spans = spans[: settings.traffic_receiver_max_spans]
            messages.append(OVER_SIZE.format(limit=settings.traffic_receiver_max_spans, count=over_size))
        allowed = await self._budget.take(project_id, len(spans))
        over_rate = len(spans) - allowed
        if over_rate:
            spans = spans[:allowed]
            messages.append(OVER_RATE.format(limit=settings.traffic_spans_per_minute, count=over_rate))
        parsed = await asyncio.to_thread(parse_spans, spans) if len(spans) > 500 else parse_spans(spans)
        config = effective_config(await self._repo.config(project_id), settings)
        scrub = scrub_of(config)
        now = utcnow()
        built = [
            build_row(
                record,
                project_id=project_id,
                source="otlp",
                scrub=scrub,
                settings=settings,
                now=now,
                prompt_version=prompt_version,
            )
            for record in parsed.records
        ]
        stored = await self._repo.insert_traces([item.values for item in built])
        await self._repo.add_ingest_counts(
            project_id,
            today,
            accepted=stored,
            ignored=parsed.ignored + len(parsed.problems),
            dropped_rate=over_rate,
            dropped_size=over_size,
        )
        await self._schedule(project_id, config.scoring_enabled)
        return ReceiveResult(stored, over_size + over_rate, " ".join(messages) or None)

    async def _schedule(self, project_id: uuid.UUID, scoring: bool) -> None:
        """Starts scoring and alert checks at most once a minute per project, and the retention purge at most once an
        hour, from the traffic itself: no separate scheduler is needed for a project that is receiving."""
        valkey = self._container.valkey
        interval = self._settings.traffic_process_interval_s
        if scoring and await valkey.set(f"traffic:process:{project_id}", "1", nx=True, ex=interval):
            self._container.jobs.enqueue(PROCESS_JOB, project_id=str(project_id))
        if await valkey.set(f"traffic:purge:{project_id}", "1", nx=True, ex=3600):
            self._container.jobs.enqueue(PURGE_JOB, project_id=str(project_id))
