"""Every import adapter on a realistic export: what is read, what is a problem, and how formats are told apart."""

from typing import Any

import pytest

from app.core.errors import ValidationFailed
from app.modules.traffic.domain import ParseResult
from app.modules.traffic.ingest import choose_adapter, load_json
from app.modules.traffic.plugins import ADAPTERS
from tests import traffic_samples as samples
from tests.traffic_samples import as_bytes


def parse(name: str, data: Any) -> ParseResult:
    from app.modules.traffic.ingest import adapters

    return adapters()[name].parse(data, 20_000)


def test_otel_reads_the_three_ways_a_prompt_can_be_recorded_and_ignores_other_spans() -> None:
    result = parse("otel", samples.otel_sample())
    by_input = {r.input_text: r for r in result.records}
    assert result.found == 6
    assert result.ignored == 1
    assert by_input["Where is my order 4471?"].output_text == "It ships tomorrow."
    assert "Reset my password" in by_input["Reset my password"].input_text  # indexed attributes
    assert by_input["Cancel my plan"].output_text == "Done, it ends this month."  # events
    failed = by_input["Refund please"]
    assert failed.status == "error"
    assert failed.error_message == "rate limited"
    first = by_input["Where is my order 4471?"]
    assert first.model == "gpt-4o-mini-2024-07-18"
    assert first.tokens_in == 41
    assert first.tokens_out == 17
    assert first.latency_ms == 850
    assert first.meta["service.name"] == "support-bot"
    assert len(result.problems) == 1
    assert "content capture" in result.problems[0].message


def test_har_keeps_the_question_and_answer_but_never_headers_cookies_or_the_query_string() -> None:
    result = parse("har", samples.har_sample())
    assert result.found == 5
    assert len(result.records) == 3
    assert [r.input_text for r in result.records][:2] == ["How do I export my data?", "What is the price?"]
    assert result.records[1].output_text == "It is 20 a month."  # base64 body decoded
    assert result.records[2].status == "error"
    stored = repr([(r.meta, r.input_text, r.output_text) for r in result.records])
    for secret in ("SUPERSECRET", "abc123", "s3cr3t", "zzz"):
        assert secret not in stored
    assert result.records[0].meta["address"] == "https://app.example.com/api/chat"
    assert len(result.problems) == 2  # the image entry has nothing to read, and the non-object entry


def test_langfuse_reads_model_prompt_version_rating_and_failures() -> None:
    result = parse("langfuse", samples.langfuse_sample())
    assert len(result.records) == 3
    assert len(result.problems) == 2
    good, bad, failed = result.records
    assert good.input_text == "Do you ship to Canada?"
    assert good.rating == 1.0
    assert bad.rating == 0.0
    assert good.model == "gpt-4o-mini"
    assert good.prompt_version == "triage@7"
    assert good.latency_ms == 1250
    assert good.tokens_in == 30
    assert good.cost == pytest.approx(0.0004)
    assert good.meta["tenant"] == "acme"
    assert good.meta["sessionId"] == "sess-1"
    assert failed.status == "error"
    assert failed.error_message == "context length exceeded"


def test_phoenix_one_record_per_trace_taken_from_its_top_span() -> None:
    result = parse("phoenix", samples.phoenix_sample())
    assert [r.input_text for r in result.records] == ["Update my address", "Delete my account"]
    assert result.records[1].status == "error"
    assert result.records[1].error_message == "timeout"
    assert result.records[0].model == "gpt-4o"
    assert result.records[0].latency_ms == 2000
    assert len(result.problems) == 1


def test_phoenix_flat_dataframe_columns_are_read_too() -> None:
    flat = [
        {
            "context.trace_id": "x",
            "context.span_id": "y",
            "span_kind": "LLM",
            "attributes.input.value": "flat question",
            "attributes.output.value": "flat answer",
        }
    ]
    assert choose_adapter(flat, "auto").name == "phoenix"
    assert parse("phoenix", flat).records[0].output_text == "flat answer"


def test_langsmith_one_record_per_trace_with_error_rating_and_cost() -> None:
    result = parse("langsmith", samples.langsmith_sample())
    assert [r.input_text for r in result.records] == ["Change my email", "Broken chain"]
    first, failed = result.records
    assert first.model == "gpt-4o-mini"
    assert first.prompt_version == "v12"
    assert first.rating == 0.0
    assert first.latency_ms == 3500
    assert first.tokens_out == 9
    assert first.cost == pytest.approx(0.0002)
    assert failed.status == "error"
    assert "boom" in (failed.error_message or "")
    assert len(result.problems) == 1


@pytest.mark.parametrize(
    ("name", "data"),
    [
        ("otel", samples.otel_sample()),
        ("har", samples.har_sample()),
        ("langfuse", samples.langfuse_sample()),
        ("phoenix", samples.phoenix_sample()),
        ("langsmith", samples.langsmith_sample()),
    ],
)
def test_each_format_is_recognised_automatically(name: str, data: Any) -> None:
    assert choose_adapter(data, "auto").name == name


def test_every_registered_format_has_a_sample_here() -> None:
    from app.modules.traffic.ingest import adapters

    assert set(adapters()) == {"otel", "har", "langfuse", "phoenix", "langsmith"} == set(ADAPTERS)


@pytest.mark.parametrize("data", [{"hello": "world"}, [1, 2, 3], "text", {"log": {}}])
def test_an_unknown_file_is_refused_with_the_list_of_formats_that_are_read(data: Any) -> None:
    with pytest.raises(ValidationFailed) as caught:
        choose_adapter(data, "auto")
    for label in ("Langfuse", "Phoenix", "LangSmith", "HAR", "OpenTelemetry"):
        assert label in caught.value.message


def test_json_lines_are_read_as_one_value_per_line_and_bad_json_names_the_line() -> None:
    lines = b'{"resourceSpans": []}\n{"resourceSpans": []}\n'
    assert load_json(lines) == [{"resourceSpans": []}, {"resourceSpans": []}]
    with pytest.raises(ValidationFailed, match="not valid JSON"):
        load_json(b'{"a": 1}\n{oops')
    with pytest.raises(ValidationFailed, match="empty"):
        load_json(b"   ")


def test_a_file_with_a_byte_order_mark_is_read() -> None:
    assert load_json(b"\xef\xbb\xbf" + as_bytes({"a": 1})) == {"a": 1}
