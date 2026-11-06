"""Reading an app's reply (ADR 0026): a small JSONPath subset, request templates that cannot break the JSON,
clear failures.
"""

import json

import pytest

from app.modules.apps.mapping import (
    MappingError,
    ResponseMapping,
    apply_mapping,
    compile_path,
    extract,
    first_or_error,
    render_request,
)

BODY = {
    "data": {"answer": "Refunds take 5 days."},
    "sources": [{"id": "a", "text": "Refund policy"}, {"id": "b", "content": "Shipping"}],
    "calls": [
        {"function": {"name": "search", "arguments": '{"q": "refund"}'}},
        {"name": "buy", "arguments": {"id": 3}},
    ],
    "usage": {"cost": 0.002},
}


def test_paths_pick_keys_indexes_and_wildcards() -> None:
    assert extract(compile_path("$.data.answer"), BODY) == ["Refunds take 5 days."]
    assert extract(compile_path("$.sources[0].id"), BODY) == ["a"]
    assert extract(compile_path("$.sources[-1].id"), BODY) == ["b"]
    assert extract(compile_path("$.sources[*].id"), BODY) == ["a", "b"]
    assert extract(compile_path("$['data']['answer']"), BODY) == ["Refunds take 5 days."]


def test_a_missing_path_says_where_it_looked_and_recursion_is_refused() -> None:
    with pytest.raises(MappingError, match=r"Nothing found at \$\.data\.reply\."):
        first_or_error("$.data.reply", BODY)
    with pytest.raises(MappingError, match="not supported"):
        compile_path("$..answer")


def test_request_templates_stay_valid_json_for_any_text() -> None:
    template = '{"question": {{ question | tojson }}, "n": 1}'
    text = 'He said "stop"\nthen left \\ and <b>ran</b>'
    assert json.loads(render_request(template, {"question": text})) == {"question": text, "n": 1}
    with pytest.raises(MappingError):
        render_request(template, {"other": "x"})  # a missing input is named, never sent blank


def test_a_reply_is_read_into_answer_chunks_tool_calls_and_cost() -> None:
    mapping = ResponseMapping("$.data.answer", "$.sources[*].text", "$.calls", "$.usage.cost")
    reply = apply_mapping(ResponseMapping("$.data.answer", "$.sources", "$.calls", "$.usage.cost"), BODY)
    assert reply.answer == "Refunds take 5 days."
    assert reply.cost == 0.002
    assert reply.chunks == ["Refund policy", "Shipping"]  # an object's text, or content
    assert reply.tool_calls == [
        {"name": "search", "arguments": {"q": "refund"}},
        {"name": "buy", "arguments": {"id": 3}},
    ]
    assert apply_mapping(mapping, {**BODY, "sources": [{"text": "Only"}]}).chunks == ["Only"]


def test_optional_paths_may_be_missing_but_the_answer_may_not() -> None:
    reply = apply_mapping(ResponseMapping("$.data.answer", "$.nope", None, None), BODY)
    assert reply.chunks == []
    assert reply.tool_calls == []
    assert reply.cost is None
    with pytest.raises(MappingError, match=r"Nothing found at \$\.answer\."):
        apply_mapping(ResponseMapping("$.answer", None, None, None), BODY)
