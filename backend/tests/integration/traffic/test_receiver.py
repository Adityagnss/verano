"""S8.8: the OTLP receiver (ingest token, gzip, caps, per-minute budget, drop counts), the purge and the scheduler."""

import gzip
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from opentelemetry.proto.collector.trace.v1 import trace_service_pb2 as service
from sqlalchemy import update

from app.core.container import Container
from app.core.jobs import JOBS, InlineJobQueue
from app.modules.traffic.models import TrafficTrace
from tests import traffic_samples as samples
from tests.helpers import Session
from tests.traffic_support import make_token, plant, send_spans, set_config, stats, tbase, trace_rows, traces

pytestmark = [pytest.mark.integration]

API_PATH = "/api/v1/otlp/v1/traces"


def payload(count: int, start: int = 1, prefix: str = "live question") -> dict[str, Any]:
    return samples.otel_export(
        [samples.otel_span(start + i, f"{prefix} {start + i}", "an answer") for i in range(count)]
    )


async def token_for(client: httpx.AsyncClient, session: Session) -> str:
    return str((await make_token(client, session))["token"])


async def test_spans_sent_with_a_token_are_stored_scrubbed_and_tagged_at_both_paths(
    client: httpx.AsyncClient, session: Session, container: Container
) -> None:
    token = await token_for(client, session)
    first = await send_spans(
        client,
        token,
        samples.otel_export([samples.otel_span(1, "mail me at ada@example.com", "ok")]),
        extra={"X-Verano-Prompt-Version": "v4"},
    )
    assert first.status_code == 200
    assert first.json() == {}
    second = await send_spans(client, token, payload(2, start=10), path=API_PATH)
    assert second.status_code == 200
    assert second.json() == {}
    listed = await traces(client, session)
    assert len(listed) == 3
    assert {t["source"] for t in listed} == {"otlp"}
    mail = next(r for r in await trace_rows(container, session) if "mail me" in r.input_text)
    assert mail.input_text == "mail me at [email]"
    assert mail.prompt_version == "v4"


async def test_the_token_is_shown_once_stored_only_as_a_hash_and_can_be_revoked(
    client: httpx.AsyncClient, session: Session
) -> None:
    created = await make_token(client, session)
    assert created["token"].startswith("vti_")
    assert created["endpoint"] == API_PATH
    listed = (await client.get(f"{tbase(session)}/tokens", headers=session.headers)).json()
    assert len(listed) == 1
    assert "token" not in listed[0]
    assert created["token"] not in str(listed)
    assert listed[0]["prefix"] == created["token"][:12]
    assert listed[0]["last_used_at"] is None
    assert (await send_spans(client, created["token"], payload(1))).status_code == 200
    used = (await client.get(f"{tbase(session)}/tokens", headers=session.headers)).json()[0]
    assert used["last_used_at"] is not None
    revoke = await client.delete(f"{tbase(session)}/tokens/{created['id']}", headers=session.headers)
    assert revoke.status_code == 204
    assert (await send_spans(client, created["token"], payload(1, start=5))).status_code == 401
    missing = await client.delete(f"{tbase(session)}/tokens/{created['id']}x", headers=session.headers)
    assert missing.status_code == 422


@pytest.mark.parametrize("token", [None, "", "nonsense", "vti_notarealtoken", "vrn_personaltokenshape"])
async def test_a_missing_or_wrong_token_is_refused_with_how_to_get_one(
    client: httpx.AsyncClient, session: Session, token: str | None
) -> None:
    response = await send_spans(client, token, payload(1))
    assert response.status_code == 401
    assert "ingest token" in response.json()["error"]["message"]
    assert await traces(client, session) == []


async def test_the_token_can_also_be_sent_in_its_own_header(client: httpx.AsyncClient, session: Session) -> None:
    token = await token_for(client, session)
    response = await client.post(
        "/v1/traces",
        content=b'{"resourceSpans": []}',
        headers={"X-Verano-Token": token, "Content-Type": "application/json"},
    )
    assert response.status_code == 200


REAL = Path(__file__).resolve().parents[2] / "fixtures" / "otlp"


@pytest.mark.parametrize(("fixture", "model"), [("openinference.pb", "gpt-4o-mini"), ("openllmetry.pb", "gpt-4o-mini")])
async def test_protobuf_from_the_real_python_exporter_is_stored_and_answered_in_protobuf(
    client: httpx.AsyncClient, session: Session, container: Container, fixture: str, model: str
) -> None:
    """The bytes are what the real `opentelemetry-exporter-otlp-proto-http` sent for a call made with the real OpenAI
    SDK, instrumented by OpenInference or OpenLLMetry (see fixtures/otlp/README.md)."""
    token = await token_for(client, session)
    raw = (REAL / fixture).read_bytes()
    response = await send_spans(client, token, None, content_type="application/x-protobuf", raw=raw)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/x-protobuf"
    assert response.content == b""  # everything was taken: an empty ExportTraceServiceResponse
    [row] = await trace_rows(container, session)
    assert (row.input_text, row.output_text, row.model) == ("How long do refunds take?", "Refunds take 30 days.", model)
    assert (row.tokens_in, row.tokens_out) == (17, 5)
    assert (
        row.source == "otlp" and len((row.external_id or "").split(":")[0]) == 32
    )  # ids are hex, like the JSON exporters send


async def test_protobuf_can_be_gzipped_is_not_stored_twice_and_reports_dropped_spans_in_protobuf(
    client: httpx.AsyncClient, session: Session, container: Container, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = await token_for(client, session)
    raw = (REAL / "openllmetry.pb").read_bytes()
    kind = "application/x-protobuf"
    assert (await send_spans(client, token, None, content_type=kind, raw=raw, gz=True)).status_code == 200
    assert (await send_spans(client, token, None, content_type=kind, raw=raw)).status_code == 200
    assert len(await trace_rows(container, session)) == 1  # the same span sent twice is stored once
    monkeypatch.setattr(container.settings, "traffic_receiver_max_spans", 1)
    many = service.ExportTraceServiceRequest()
    many.ParseFromString(raw)
    span = many.resource_spans[0].scope_spans[0].spans[0]
    for number in range(3):
        extra = many.resource_spans[0].scope_spans[0].spans.add()
        extra.CopyFrom(span)
        extra.span_id = bytes([number + 1]) * 8
    answer = await send_spans(client, token, None, content_type=kind, raw=many.SerializeToString())
    assert answer.status_code == 200
    reply = service.ExportTraceServiceResponse()
    reply.ParseFromString(answer.content)
    assert reply.partial_success.rejected_spans == 3 and "1 spans" in reply.partial_success.error_message


async def test_a_protobuf_body_that_is_not_otlp_is_refused_and_other_media_types_say_what_is_accepted(
    client: httpx.AsyncClient, session: Session
) -> None:
    token = await token_for(client, session)
    broken = await send_spans(client, token, None, content_type="application/x-protobuf", raw=b"not protobuf at all")
    assert broken.status_code == 422 and "not a valid OTLP request" in broken.json()["error"]["message"]
    other = await send_spans(client, token, None, content_type="text/plain", raw=b"hello")
    assert other.status_code == 415
    assert "application/x-protobuf" in other.json()["error"]["message"]
    assert await traces(client, session) == []


@pytest.mark.parametrize(("raw", "words"), [(b"{broken", "not a valid OTLP"), (b"   ", "empty")])
async def test_a_broken_or_empty_body_is_refused_and_nothing_is_stored(
    client: httpx.AsyncClient, session: Session, raw: bytes, words: str
) -> None:
    token = await token_for(client, session)
    response = await send_spans(client, token, None, raw=raw)
    assert response.status_code == 422
    assert words in response.json()["error"]["message"]
    assert await traces(client, session) == []


async def test_a_gzip_body_is_unpacked_and_a_corrupt_one_is_refused(
    client: httpx.AsyncClient, session: Session
) -> None:
    token = await token_for(client, session)
    assert (await send_spans(client, token, payload(3), gz=True)).status_code == 200
    assert len(await traces(client, session)) == 3
    broken = await client.post(
        "/v1/traces",
        content=b"definitely not gzip",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Content-Encoding": "gzip"},
    )
    assert broken.status_code == 422


async def chunks() -> Any:
    for chunk in (b"x" * 1_500, b"x" * 1_500):
        yield chunk


async def test_a_too_large_request_is_dropped_with_413_and_counted(
    client: httpx.AsyncClient, session: Session, container: Container
) -> None:
    token = await token_for(client, session)
    container.settings.traffic_receiver_max_bytes = 2_000
    try:
        big = await send_spans(client, token, payload(40))
        assert big.status_code == 413
        assert "larger than" in big.json()["error"]["message"]
        streamed = await client.post(  # no Content-Length: read in chunks and cut at the limit
            "/v1/traces",
            content=chunks(),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        assert streamed.status_code == 413
    finally:
        container.settings.traffic_receiver_max_bytes = 4_000_000
    assert await traces(client, session) == []
    seen = await stats(client, session)
    assert seen["days"][-1]["rejected_requests"] == 2
    assert seen["dropped_recent"] == 2


async def test_a_gzip_bomb_is_stopped_at_the_size_limit_and_counted(
    client: httpx.AsyncClient, session: Session, container: Container
) -> None:
    token = await token_for(client, session)
    bomb = gzip.compress(b'{"resourceSpans": [' + b" " * 50_000_000 + b"]}")
    assert len(bomb) < 100_000  # tiny on the wire, huge when unpacked
    container.settings.traffic_receiver_max_bytes = 1_000_000
    try:
        response = await client.post(
            "/v1/traces",
            content=bomb,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Content-Encoding": "gzip",
            },
        )
    finally:
        container.settings.traffic_receiver_max_bytes = 4_000_000
    assert response.status_code == 413
    assert (await stats(client, session))["days"][-1]["rejected_requests"] == 1


async def test_spans_over_the_per_request_cap_are_dropped_and_the_reply_says_how_many(
    client: httpx.AsyncClient, session: Session, container: Container
) -> None:
    token = await token_for(client, session)
    container.settings.traffic_receiver_max_spans = 5
    try:
        response = await send_spans(client, token, payload(8))
    finally:
        container.settings.traffic_receiver_max_spans = 2_000
    assert response.status_code == 200
    partial = response.json()["partialSuccess"]
    assert partial["rejectedSpans"] == 3
    assert "at most 5 spans" in partial["errorMessage"]
    assert len(await traces(client, session)) == 5
    day = (await stats(client, session))["days"][-1]
    assert day["accepted"] == 5
    assert day["dropped_size"] == 3
    assert day["dropped_rate"] == 0


async def test_spans_over_the_per_minute_budget_are_dropped_and_counted_for_the_day(
    client: httpx.AsyncClient, session: Session, container: Container
) -> None:
    token = await token_for(client, session)
    container.settings.traffic_spans_per_minute = 10
    try:
        first = await send_spans(client, token, payload(8))
        second = await send_spans(client, token, payload(8, start=100))
        third = await send_spans(client, token, payload(2, start=200))
    finally:
        container.settings.traffic_spans_per_minute = 60_000
    assert first.json() == {}
    assert second.json()["partialSuccess"]["rejectedSpans"] == 6
    assert "10 spans a minute" in second.json()["partialSuccess"]["errorMessage"]
    assert third.json()["partialSuccess"]["rejectedSpans"] == 2  # the minute is already used up
    assert len(await traces(client, session)) == 10
    seen = await stats(client, session)
    assert seen["days"][-1]["dropped_rate"] == 8
    assert seen["dropped_recent"] == 8
    assert seen["total"] == 10


async def test_each_project_has_its_own_minute_budget(
    client: httpx.AsyncClient, session: Session, container: Container
) -> None:
    from tests.helpers import sign_up

    other_headers = await sign_up(client, "second-owner@example.com")
    project = (await client.post("/api/v1/projects", json={"name": "Other"}, headers=other_headers)).json()
    other = (
        await client.post(f"/api/v1/projects/{project['id']}/traffic/tokens", json={"name": "t"}, headers=other_headers)
    ).json()
    mine = await token_for(client, session)
    container.settings.traffic_spans_per_minute = 5
    try:
        assert (await send_spans(client, mine, payload(5))).json() == {}
        assert (await send_spans(client, other["token"], payload(5, start=50))).json() == {}
    finally:
        container.settings.traffic_spans_per_minute = 60_000


async def test_spans_that_are_not_model_calls_are_ignored_and_resending_a_span_stores_it_once(
    client: httpx.AsyncClient, session: Session
) -> None:
    token = await token_for(client, session)
    mixed = samples.otel_export([samples.otel_span(1, "one", "a"), samples.database_span(1)])
    assert (await send_spans(client, token, mixed)).status_code == 200
    assert (await send_spans(client, token, mixed)).status_code == 200
    assert len(await traces(client, session)) == 1
    day = (await stats(client, session))["days"][-1]
    assert day["accepted"] == 1
    assert day["ignored"] == 2


async def test_a_thousand_span_batch_is_stored_in_one_request(client: httpx.AsyncClient, session: Session) -> None:
    token = await token_for(client, session)
    response = await send_spans(client, token, payload(1_000), gz=True)
    assert response.status_code == 200
    assert response.json() == {}
    assert (await stats(client, session))["total"] == 1_000


# ---------------------------------------------------------------------------------- retention and scheduler


async def age(container: Container, session: Session, days: int, texts: list[str]) -> None:
    async with container.database.sessions() as db:
        await db.execute(
            update(TrafficTrace)
            .where(TrafficTrace.project_id == session.project_id, TrafficTrace.input_text.in_(texts))
            .values(created_at=datetime.now(UTC) - timedelta(days=days))
        )
        await db.commit()


async def test_the_retention_purge_deletes_only_traces_older_than_the_retention_period(
    client: httpx.AsyncClient, session: Session, container: Container
) -> None:
    token = await token_for(client, session)
    await send_spans(client, token, samples.otel_export([samples.otel_span(i, f"q{i}", "a") for i in range(1, 6)]))
    await set_config(client, session, retention_days=7)
    await age(container, session, 10, ["q1", "q2"])
    await age(container, session, 6, ["q3"])
    purged = await client.post(f"{tbase(session)}/purge", headers=session.headers)
    assert purged.status_code == 200
    assert purged.json() == {"deleted": 2}
    assert sorted(t["input_preview"] for t in await traces(client, session)) == ["q3", "q4", "q5"]
    assert (await client.post(f"{tbase(session)}/purge", headers=session.headers)).json() == {"deleted": 0}


async def test_purge_never_touches_another_projects_traces(
    client: httpx.AsyncClient, session: Session, container: Container
) -> None:
    from tests.helpers import sign_up

    await plant(container, session, [(0, 1, 2)])
    await set_config(client, session, retention_days=1)
    await age(container, session, 30, ["planted question 0 0"])
    headers = await sign_up(client, "bystander@example.com")
    project = (await client.post("/api/v1/projects", json={"name": "Bystander"}, headers=headers)).json()
    other = Session(headers, session.user_id, project["id"])
    await plant(container, other, [(0, 1, 1)])
    await age(container, other, 30, ["planted question 0 0"])
    await client.post(f"{tbase(session)}/purge", headers=session.headers)
    assert len(await trace_rows(container, session)) == 1
    assert len(await trace_rows(container, other)) == 1


async def test_the_scheduled_sweep_purges_idle_projects_without_any_incoming_traffic(
    client: httpx.AsyncClient, session: Session, container: Container, jobs: InlineJobQueue
) -> None:
    token = await token_for(client, session)
    await send_spans(client, token, samples.otel_export([samples.otel_span(i, f"s{i}", "a") for i in range(1, 4)]))
    await jobs.drain()
    await set_config(client, session, retention_days=7)
    await age(container, session, 10, ["s1"])
    await container.valkey.flushall()  # the receiver's once-an-hour purge key is gone, as after an idle hour
    container.jobs.enqueue("traffic.sweep")
    await jobs.drain()
    assert sorted(t["input_preview"] for t in await traces(client, session)) == ["s2", "s3"]


async def test_the_sweep_is_registered_with_celery_beat_next_to_the_lease_sweeper() -> None:
    from app.workers.celery_app import celery_app

    schedule = celery_app.conf.beat_schedule
    assert schedule["sweep-leases"]["task"] == "engine.sweep_leases"
    assert schedule["sweep-traffic"]["task"] == "traffic.sweep"
    assert schedule["sweep-traffic"]["schedule"] > 0
    assert {"traffic.sweep", "traffic.process", "traffic.purge"} <= set(JOBS)
