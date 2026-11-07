"""S8.6: importing traces from files of each supported tool; scrubbing; caps; the list and one trace; repeat imports."""

from typing import Any

import httpx
import pytest

from app.core.container import Container
from tests import traffic_samples as samples
from tests.helpers import Session
from tests.traffic_support import import_data, set_config, tbase, trace_rows, traces

pytestmark = [pytest.mark.integration]

FORMATS = [
    ("otel", samples.otel_sample, 4, "Where is my order 4471?"),
    ("har", samples.har_sample, 3, "How do I export my data?"),
    ("langfuse", samples.langfuse_sample, 3, "Do you ship to Canada?"),
    ("phoenix", samples.phoenix_sample, 2, "Update my address"),
    ("langsmith", samples.langsmith_sample, 2, "Change my email"),
]


@pytest.mark.parametrize(("name", "build", "count", "first"), FORMATS)
async def test_a_file_of_each_format_is_recognised_and_its_traces_are_listed(
    client: httpx.AsyncClient, session: Session, name: str, build: Any, count: int, first: str
) -> None:
    response = await import_data(client, session, build())
    assert response.status_code == 201, response.text
    report = response.json()
    assert report["format"] == name
    assert report["imported"] == count
    assert report["duplicates"] == 0
    listed = await traces(client, session)
    assert len(listed) == count
    assert all(t["source"] == name for t in listed)
    one = next(t for t in listed if t["input_preview"] == first)
    detail = (await client.get(f"{tbase(session)}/{one['id']}", headers=session.headers)).json()
    assert detail["input_text"] == first
    assert detail["output_text"]
    assert detail["status"] in ("ok", "error")
    assert isinstance(detail["meta"], dict)


async def test_naming_the_format_reads_the_file_that_way_and_a_wrong_choice_stores_nothing_and_says_why(
    client: httpx.AsyncClient, session: Session
) -> None:
    ok = await import_data(client, session, samples.langfuse_sample(), fmt="langfuse")
    assert ok.status_code == 201
    assert ok.json()["imported"] == 3
    wrong = await import_data(client, session, samples.har_sample(), fmt="langsmith")
    assert wrong.status_code == 201
    assert wrong.json()["imported"] == 0
    assert wrong.json()["problems"]
    empty = await import_data(client, session, {"runs": []}, fmt="langsmith")
    assert empty.status_code == 422
    assert "No LangSmith traces" in empty.json()["error"]["message"]
    unknown = await import_data(client, session, samples.har_sample(), fmt="datadog")
    assert unknown.status_code == 422
    assert "datadog" in unknown.json()["error"]["message"]


async def test_an_unknown_file_gets_a_message_that_lists_the_formats_and_stores_nothing(
    client: httpx.AsyncClient, session: Session, container: Container
) -> None:
    response = await import_data(client, session, {"customers": [{"name": "Ada"}]})
    assert response.status_code == 422
    message = response.json()["error"]["message"]
    assert "could not tell which tool" in message
    assert "Langfuse" in message
    assert "HAR" in message
    assert await trace_rows(container, session) == []


@pytest.mark.parametrize(
    ("raw", "words"),
    [(b"", "empty"), (b"{not json at all", "not valid JSON"), (b'{"a": 1}\n{oops', "not valid JSON")],
)
async def test_an_empty_or_broken_file_is_refused_in_plain_words(
    client: httpx.AsyncClient, session: Session, raw: bytes, words: str
) -> None:
    response = await import_data(client, session, None, raw=raw)
    assert response.status_code == 422
    assert words in response.json()["error"]["message"]


async def test_bad_records_are_reported_by_position_and_the_good_ones_are_still_stored(
    client: httpx.AsyncClient, session: Session
) -> None:
    report = (await import_data(client, session, samples.langfuse_sample())).json()
    assert report["imported"] == 3
    assert len(report["problems"]) == 2
    assert {p["record"] for p in report["problems"]} == {4, 5}
    assert all(p["message"] for p in report["problems"])
    assert report["more_problems"] == 0
    otel = (await import_data(client, session, samples.otel_sample())).json()
    assert otel["ignored"] == 1
    assert any("content capture" in p["message"] for p in otel["problems"])


async def test_importing_the_same_file_twice_stores_each_trace_once(
    client: httpx.AsyncClient, session: Session
) -> None:
    for build in (samples.otel_sample, samples.har_sample, samples.langsmith_sample):  # HAR has no ids: by content
        first = (await import_data(client, session, build())).json()
        again = (await import_data(client, session, build())).json()
        assert again["imported"] == 0
        assert again["duplicates"] == first["imported"]
    assert len(await traces(client, session)) == 4 + 3 + 2


async def test_the_same_trace_ids_from_two_tools_are_kept_apart_by_source(
    client: httpx.AsyncClient, session: Session
) -> None:
    await import_data(client, session, samples.langfuse_sample())
    other = samples.langfuse_sample()
    await import_data(client, session, other, fmt="langfuse")  # same ids: duplicates
    assert len(await traces(client, session)) == 3


async def test_personal_data_is_replaced_before_anything_is_stored_and_counted(
    client: httpx.AsyncClient, session: Session, container: Container
) -> None:
    data = samples.otel_export(
        [
            samples.otel_span(
                1,
                "Hi, I am ada@example.com, call me on +44 20 7946 0958, card 4111 1111 1111 1111",
                "Thanks ada@example.com, we will call +44 20 7946 0958.",
            )
        ]
    )
    report = (await import_data(client, session, data)).json()
    assert report["scrubbed"] == 5
    row = (await trace_rows(container, session))[0]
    assert "@" not in row.input_text
    assert "7946" not in row.input_text
    assert "4111" not in row.input_text
    assert row.input_text == "Hi, I am [email], call me on [phone], card [card]"
    assert row.output_text == "Thanks [email], we will call [phone]."
    assert row.scrubbed_count == 5
    listed = (await traces(client, session))[0]
    assert listed["scrubbed_count"] == 5


async def test_the_owners_own_pattern_is_applied_and_a_risky_pattern_is_refused(
    client: httpx.AsyncClient, session: Session, container: Container
) -> None:
    refused = await client.put(f"{tbase(session)}/config", json={"scrub_patterns": ["(a+)+$"]}, headers=session.headers)
    assert refused.status_code == 422
    await set_config(client, session, scrub_patterns=[r"ACME-\d{6}"])
    data = samples.otel_export([samples.otel_span(1, "My account ACME-123456 is locked", "Unlocked.")])
    await import_data(client, session, data)
    assert (await trace_rows(container, session))[0].input_text == "My account [hidden] is locked"


async def test_scrubbing_can_be_switched_off_for_a_project(
    client: httpx.AsyncClient, session: Session, container: Container
) -> None:
    await set_config(client, session, scrub_pii=False)
    data = samples.otel_export([samples.otel_span(1, "write to ada@example.com", "ok")])
    assert (await import_data(client, session, data)).json()["scrubbed"] == 0
    assert (await trace_rows(container, session))[0].input_text == "write to ada@example.com"


async def test_a_har_file_never_stores_headers_cookies_or_the_query_string(
    client: httpx.AsyncClient, session: Session, container: Container
) -> None:
    await import_data(client, session, samples.har_sample())
    everything = repr([(r.meta, r.input_text, r.output_text) for r in await trace_rows(container, session)])
    for secret in ("SUPERSECRET", "abc123", "s3cr3t", "Cookie", "Authorization"):
        assert secret not in everything


async def test_long_texts_are_cut_to_the_cap_and_flagged_and_short_ones_are_not(
    client: httpx.AsyncClient, session: Session, container: Container
) -> None:
    limit = container.settings.traffic_field_max_chars
    data = samples.otel_export(
        [
            samples.otel_span(1, "q" * (limit + 500), "short answer"),
            samples.otel_span(2, "short question", "a" * (limit + 1)),
            samples.otel_span(3, "plain", "plain"),
        ]
    )
    report = (await import_data(client, session, data)).json()
    assert report["truncated"] == 2
    by_input = {r.input_text[:5]: r for r in await trace_rows(container, session)}
    assert len(by_input["qqqqq"].input_text) == limit
    assert by_input["qqqqq"].input_truncated
    assert not by_input["qqqqq"].output_truncated
    assert by_input["short"].output_truncated
    assert len(by_input["short"].output_text) == limit
    assert not by_input["plain"].input_truncated
    assert not by_input["plain"].output_truncated
    flags = {t["input_preview"][:5]: t for t in await traces(client, session)}
    assert flags["qqqqq"]["input_truncated"]
    assert not flags["plain"]["input_truncated"]


async def test_huge_metadata_is_bounded_and_flagged(
    client: httpx.AsyncClient, session: Session, container: Container
) -> None:
    span = samples.otel_span(1, "q", "a")
    span["attributes"] += [samples._s(f"custom.key{i}", "x" * 400) for i in range(60)]
    report = (await import_data(client, session, samples.otel_export([span]))).json()
    assert report["truncated"] == 1
    row = (await trace_rows(container, session))[0]
    assert len(row.meta) <= 40


async def test_a_file_over_the_size_limit_is_refused_with_how_to_split_it(
    client: httpx.AsyncClient, session: Session, container: Container
) -> None:
    container.settings.traffic_import_max_bytes = 500
    try:
        response = await import_data(client, session, samples.langfuse_sample())
    finally:
        container.settings.traffic_import_max_bytes = 50_000_000
    assert response.status_code == 422
    assert "Split it" in response.json()["error"]["message"]


async def test_records_beyond_the_per_file_cap_are_not_read(
    client: httpx.AsyncClient, session: Session, container: Container
) -> None:
    container.settings.traffic_import_max_records = 2
    try:
        report = (await import_data(client, session, samples.langfuse_sample())).json()
    finally:
        container.settings.traffic_import_max_records = 20_000
    assert report["found"] == 5
    assert report["imported"] == 2


async def test_the_prompt_version_tag_fills_in_only_where_the_file_has_none(
    client: httpx.AsyncClient, session: Session
) -> None:
    await import_data(client, session, samples.har_sample(), prompt_version="v9")
    await import_data(client, session, samples.langfuse_sample(), prompt_version="v9")
    by_source: dict[str, set[str | None]] = {}
    for t in await traces(client, session):
        by_source.setdefault(t["source"], set()).add(t["prompt_version"])
    assert by_source["har"] == {"v9"}
    assert by_source["langfuse"] == {"triage@7"}


async def test_the_list_filters_find_failed_low_rated_long_and_searched_traces(
    client: httpx.AsyncClient, session: Session
) -> None:
    await import_data(client, session, samples.langfuse_sample())
    await import_data(client, session, samples.har_sample())
    failed = await traces(client, session, failed=True)
    assert {t["status"] for t in failed} == {"error"}
    assert len(failed) == 2
    low = await traces(client, session, low_rated=True)
    assert [t["input_preview"] for t in low] == ["My card was declined"]
    assert [t["input_preview"] for t in await traces(client, session, q="Canada")] == ["Do you ship to Canada?"]
    assert len(await traces(client, session, source="har")) == 3
    assert await traces(client, session, long=True) == []  # nothing took 10 seconds
    assert len(await traces(client, session, prompt_version="triage@7")) == 3


async def test_the_list_pages_with_a_cursor_and_a_trace_can_be_deleted(
    client: httpx.AsyncClient, session: Session
) -> None:
    spans = [samples.otel_span(i, f"question number {i}", "answer") for i in range(1, 8)]
    await import_data(client, session, samples.otel_export(spans))
    first = (await client.get(tbase(session), params={"limit": 3}, headers=session.headers)).json()
    assert len(first["items"]) == 3
    assert first["next_cursor"]
    assert len(await traces(client, session)) == 7
    target = first["items"][0]["id"]
    assert (await client.delete(f"{tbase(session)}/{target}", headers=session.headers)).status_code == 204
    assert (await client.get(f"{tbase(session)}/{target}", headers=session.headers)).status_code == 404
    assert (await client.delete(f"{tbase(session)}/{target}", headers=session.headers)).status_code == 404


async def test_formats_endpoint_lists_every_format_with_a_hint(client: httpx.AsyncClient, session: Session) -> None:
    found = (await client.get(f"{tbase(session)}/formats", headers=session.headers)).json()
    assert {f["name"] for f in found} == {"otel", "har", "langfuse", "phoenix", "langsmith"}
    assert all(f["label"] and f["hint"] for f in found)


async def test_another_project_cannot_see_or_import_into_these_traces(
    client: httpx.AsyncClient, session: Session
) -> None:
    from tests.helpers import sign_up

    await import_data(client, session, samples.har_sample())
    stranger = await sign_up(client, "stranger@example.com")
    assert (await client.get(tbase(session), headers=stranger)).status_code in (403, 404)
    response = await client.post(
        f"{tbase(session)}/import", files={"file": ("a.json", b"{}", "application/json")}, headers=stranger
    )
    assert response.status_code in (403, 404)
    assert (await client.get(tbase(session))).status_code == 401
