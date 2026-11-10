"""The integrations people plug into their own code: `verano.test` and `verano.serve`, the pytest plugin, the
LangChain, LlamaIndex and OpenAI adapters (against stand-in objects: the real libraries are optional extras), and the
MCP server for AI agents (ADR 0033)."""

import importlib
import io
import json
import subprocess
import sys
import urllib.request
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tests.platform import FakePlatform
from verano import adapters, auth, testing
from verano.client import ApiClient
from verano.errors import CliError
from verano.mcp.protocol import SUPPORTED_VERSIONS, Server
from verano.mcp.tools import REFUSAL, WRITE_FLAG, Context, registry
from verano.testing import Case, Reply


@pytest.fixture(autouse=True)
def _clean_recorder() -> Any:
    """`verano.test` records into a global that the pytest plugin prints at the end of this very run."""
    testing.RECORDER.clear()
    yield
    testing.RECORDER.clear()


# -- verano.test and verano.serve ---------------------------------------------------------------------------


def test_a_case_passes_when_every_check_holds_and_is_recorded() -> None:
    testing.RECORDER.clear()
    reply = testing.test(
        Case(input="refund?", contains=("refund",), not_contains=("password",), regex=r"\d+ days", name="refunds"),
        lambda text: f"You can get a refund within 30 days ({text}).",
    )
    assert reply.answer.startswith("You can get a refund")
    assert [(r.name, r.passed) for r in testing.RECORDER] == [("refunds", True)]


def test_a_failing_case_names_every_problem_in_plain_words() -> None:
    testing.RECORDER.clear()
    case = Case(input="x", expected="billing", contains=("invoice",), not_contains=("sorry",), regex=r"^\d+$")
    with pytest.raises(AssertionError) as failure:
        testing.test(case, lambda _: "Sorry, shipping")
    text = str(failure.value)
    assert "expected 'billing' but the answer was 'Sorry, shipping'" in text
    assert "should contain 'invoice'" in text
    assert "should not contain 'sorry'" in text
    assert "pattern" in text
    assert testing.RECORDER[0].passed is False
    assert len(testing.RECORDER[0].problems) == 4


def test_the_expected_answer_ignores_case_and_spacing() -> None:
    assert testing.test(Case(input="x", expected="Billing  Team"), lambda _: "billing team").answer == "billing team"


@pytest.mark.parametrize(
    ("raw", "answer", "chunks", "tools"),
    [
        ("plain text", "plain text", [], []),
        ({"answer": "a", "chunks": ["c1", {"page_content": "c2"}]}, "a", ["c1", "c2"], []),
        ({"output": "o", "source_documents": [SimpleNamespace(page_content="doc")]}, "o", ["doc"], []),
        ({"text": "t", "tool_calls": [{"name": "lookup", "arguments": "{}"}, "ignored"]}, "t", [], ["lookup"]),
        (SimpleNamespace(content="from a chat message"), "from a chat message", [], []),
        (Reply("already", ["x"]), "already", ["x"], []),
    ],
)
def test_results_from_any_library_become_one_reply(raw: Any, answer: str, chunks: list[str], tools: list[str]) -> None:
    reply = testing.normalize(raw)
    assert (reply.answer, reply.chunks, [t["name"] for t in reply.tool_calls]) == (answer, chunks, tools)


def post(url: str, body: dict[str, Any] | bytes) -> tuple[int, dict[str, Any]]:
    data = body if isinstance(body, bytes) else json.dumps(body).encode()
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def test_serve_answers_verano_app_calls_with_the_function_and_reports_its_failures() -> None:
    def app(text: str) -> Any:
        if text == "boom":
            raise RuntimeError("the model is down")
        return Reply(f"echo {text}", ["a chunk"], [{"name": "search", "arguments": "{}"}])

    with testing.serve(app) as server:
        assert post(server.url, {"input": "hi"}) == (
            200,
            {"answer": "echo hi", "chunks": ["a chunk"], "tool_calls": [{"name": "search", "arguments": "{}"}]},
        )
        status, body = post(server.url, {"input": "boom"})
        assert status == 500
        assert "Your function failed: the model is down" in body["error"]


# -- the pytest plugin --------------------------------------------------------------------------------------


def test_the_plugin_prints_a_summary_and_writes_a_json_report(tmp_path: Path) -> None:
    (tmp_path / "test_app.py").write_text(
        "import verano\n"
        "def answer(text): return 'refunds take 30 days'\n"
        "def test_good(): verano.testing.test(verano.testing.Case('x', contains=('30 days',), name='good'), answer)\n"
        "def test_bad(): verano.testing.test(verano.testing.Case('x', contains=('90 days',), name='bad'), answer)\n"
    )
    report = tmp_path / "report.json"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--verano-report={report}"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 1  # the bad case fails the test
    assert "Verano checks" in result.stdout
    assert "2 cases checked, 1 passed, 1 failed." in result.stdout
    assert "failed: bad:" in result.stdout
    assert f"Report written to {report}." in result.stdout
    data = json.loads(report.read_text())
    assert (data["passed"], data["failed"]) == (1, 1)
    assert {c["name"]: c["passed"] for c in data["cases"]} == {"good": True, "bad": False}


# -- adapters, against stand-in objects ---------------------------------------------------------------------


@pytest.fixture
def installed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(adapters, "_require", lambda module, extra: None)


def test_the_langchain_adapter_sends_the_input_as_given_or_under_a_key(installed: None) -> None:
    seen: list[Any] = []

    def invoke(payload: Any) -> dict[str, Any]:
        seen.append(payload)
        return {"answer": "ok", "context": ["c"]}

    runnable = SimpleNamespace(invoke=invoke)
    assert adapters.langchain(runnable)("question") == Reply("ok", ["c"])
    assert adapters.langchain(runnable, input_key="question")("q2").answer == "ok"
    assert seen == ["question", {"question": "q2"}]


def test_the_llamaindex_adapter_returns_the_response_and_the_retrieved_nodes(installed: None) -> None:
    nodes = [
        SimpleNamespace(node=SimpleNamespace(get_content=lambda: "from node")),
        SimpleNamespace(text="from text"),
    ]
    engine = SimpleNamespace(query=lambda text: SimpleNamespace(response=f"answer to {text}", source_nodes=nodes))
    assert adapters.llamaindex(engine)(42) == Reply("answer to 42", ["from node", "from text"])


def test_the_openai_adapter_sends_the_system_prompt_and_reports_tool_calls(installed: None) -> None:
    sent: dict[str, Any] = {}

    def create(**kwargs: Any) -> Any:
        sent.update(kwargs)
        call = SimpleNamespace(function=SimpleNamespace(name="get_weather", arguments='{"city": "Oslo"}'))
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=None, tool_calls=[call]))])

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    reply = adapters.openai(client, "gpt-4o-mini", system="Be brief.", temperature=0)("weather?")
    assert sent["messages"] == [{"role": "system", "content": "Be brief."}, {"role": "user", "content": "weather?"}]
    assert sent["model"] == "gpt-4o-mini"
    assert sent["temperature"] == 0
    assert reply == Reply("", [], [{"name": "get_weather", "arguments": '{"city": "Oslo"}'}])


def test_a_missing_library_says_which_extra_to_install(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(name: str) -> Any:
        raise ImportError(name)

    monkeypatch.setattr(importlib, "import_module", refuse)
    with pytest.raises(CliError) as failure:
        adapters.openai(object(), "m")
    assert "needs the openai package" in failure.value.message
    assert "verano[openai]" in str(failure.value.hint)


# -- the MCP server -----------------------------------------------------------------------------------------


def rpc(server: Server, method: str, params: dict[str, Any] | None = None, identifier: int = 1) -> dict[str, Any]:
    reply = server.handle({"jsonrpc": "2.0", "id": identifier, "method": method, "params": params or {}})
    assert reply is not None
    return reply


def offline(allow_write: bool = False, max_cost: Decimal | None = None) -> Server:
    """A server whose API client is never used: enough for everything that is refused before it reaches Verano."""
    return Server(Context(api=None, base_url="http://verano.test", allow_write=allow_write, max_cost=max_cost))  # type: ignore[arg-type]


def test_the_server_agrees_a_protocol_version_and_says_who_it_is() -> None:
    server = offline()
    assert (
        rpc(server, "initialize", {"protocolVersion": SUPPORTED_VERSIONS[1]})["result"]["protocolVersion"]
        == (SUPPORTED_VERSIONS[1])
    )
    reply = rpc(server, "initialize", {"protocolVersion": "1999-01-01"})["result"]
    assert reply["protocolVersion"] == SUPPORTED_VERSIONS[0]
    assert reply["serverInfo"]["name"] == "verano"
    assert "--allow-write" in reply["instructions"]
    assert rpc(server, "ping")["result"] == {}


def test_every_tool_is_listed_with_schemas_and_the_writing_ones_are_marked() -> None:
    tools = {t["name"]: t for t in rpc(offline(), "tools/list")["result"]["tools"]}
    assert set(tools) == {t.name for t in registry()}
    assert len(tools) == 10
    for tool in registry():
        listed = tools[tool.name]
        assert listed["inputSchema"]["type"] == "object"
        assert listed["outputSchema"]["type"] == "object"
        assert listed["annotations"]["readOnlyHint"] is (not tool.writes)
        assert ("--allow-write" in listed["description"]) is tool.writes
    assert {n for n, t in tools.items() if not t["annotations"]["readOnlyHint"]} == {
        "create_project",
        "run_evaluation",
        "propose_improvement",
        "accept_improvement",
        "move_label",
    }


@pytest.mark.parametrize(
    "tool", ["create_project", "run_evaluation", "propose_improvement", "accept_improvement", "move_label"]
)
def test_a_writing_tool_is_refused_without_the_flag_and_the_refusal_names_it(tool: str) -> None:
    result = rpc(offline(), "tools/call", {"name": tool, "arguments": {}})["result"]
    assert result["isError"] is True
    assert result["content"][0]["text"] == REFUSAL.format(tool=tool, flag=WRITE_FLAG)


def test_bad_calls_are_answered_in_words_and_never_crash_the_server() -> None:
    server = offline(allow_write=True)
    unknown = rpc(server, "tools/call", {"name": "nope", "arguments": {}})["result"]
    assert unknown["isError"]
    assert "There is no tool called nope" in unknown["content"][0]["text"]
    invalid = rpc(server, "tools/call", {"name": "create_project", "arguments": {"surprise": 1}})["result"]
    assert invalid["isError"]
    assert "not valid" in invalid["content"][0]["text"]
    assert rpc(server, "tools/call", {"arguments": {}})["error"]["code"] == -32602
    assert rpc(server, "no/such/method")["error"]["code"] == -32601
    assert server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None  # no answer to a notice
    assert server.handle(["not", "a", "request"])["error"]["code"] == -32600  # type: ignore[index]


def test_the_server_reads_lines_answers_lines_and_survives_garbage() -> None:
    lines = [
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}),
        "this is not json",
        "",
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
    ]
    sink, log = io.StringIO(), list[str]()
    offline().serve(io.StringIO("\n".join(lines) + "\n"), sink, log.append)
    answers = [json.loads(line) for line in sink.getvalue().splitlines()]
    assert [a.get("id") for a in answers] == [1, None, 2]
    assert answers[1]["error"]["code"] == -32700
    assert "tools" in answers[2]["result"]
    assert log == ["Input closed; the Verano MCP server stopped."]


def test_a_read_tool_reads_and_a_write_tool_writes_only_with_the_flag(platform: FakePlatform) -> None:
    api = ApiClient.from_credentials(auth.signed_in())
    readonly = Server(Context(api, "http://verano.test", allow_write=False))
    assert rpc(readonly, "tools/call", {"name": "list_projects", "arguments": {}})["result"]["isError"] is False
    assert platform.writes == []  # nothing was written
    writer = Server(Context(api, "http://verano.test", allow_write=True))
    made = rpc(writer, "tools/call", {"name": "create_project", "arguments": {"name": "From an agent"}})["result"]
    assert made["isError"] is False
    assert made["structuredContent"]["name"] == "From an agent"
    listed = rpc(readonly, "tools/call", {"name": "list_projects", "arguments": {}})["result"]["structuredContent"]
    assert "From an agent" in json.dumps(listed)
