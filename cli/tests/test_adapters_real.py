"""The adapters against the REAL LangChain, LlamaIndex and OpenAI libraries. These are optional extras, so each test is
skipped when its library is missing (as in a normal run). To run them: install the libraries beside Verano in a spare
environment (`uv pip install -e . langchain-core openai llama-index-core pytest`) and run this file there. The OpenAI
client is the real SDK talking HTTP to a tiny local server, so no key and no network are used."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

from verano import adapters
from verano.testing import Case, test


def test_a_real_langchain_chain_is_checked_through_the_adapter() -> None:
    pytest.importorskip("langchain_core")
    from langchain_core.language_models.fake_chat_models import FakeListChatModel
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.runnables import RunnableLambda

    chain = ChatPromptTemplate.from_messages([("human", "Route this ticket: {ticket}")]) | FakeListChatModel(
        responses=["billing"]
    )
    reply = test(Case(input="card charged twice", expected="billing"), adapters.langchain(chain, input_key="ticket"))
    assert reply.answer == "billing"

    rag = RunnableLambda(lambda question: {"answer": f"about {question}", "context": ["chunk one", "chunk two"]})
    assert adapters.langchain(rag)("refunds").chunks == ["chunk one", "chunk two"]


def test_a_real_llamaindex_query_engine_returns_its_answer_and_the_retrieved_text() -> None:
    pytest.importorskip("llama_index.core")
    from llama_index.core import Document, Settings, VectorStoreIndex
    from llama_index.core.embeddings import MockEmbedding
    from llama_index.core.llms import MockLLM

    Settings.llm = MockLLM()
    Settings.embed_model = MockEmbedding(embed_dim=8)
    engine = VectorStoreIndex.from_documents([Document(text="Refunds are paid within 30 days.")]).as_query_engine()
    reply = adapters.llamaindex(engine)("How long do refunds take?")
    assert reply.answer
    assert any("Refunds are paid within 30 days." in chunk for chunk in reply.chunks)


class FakeOpenAI(BaseHTTPRequestHandler):
    """Answers /chat/completions like OpenAI: plain text, or a tool call when the question mentions the weather."""

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        weather = "weather" in json.dumps(body["messages"])
        message: dict[str, Any] = {"role": "assistant", "content": None if weather else "billing"}
        if weather:
            message["tool_calls"] = [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "get_weather", "arguments": '{"city": "Oslo"}'},
                }
            ]
        answer = {
            "id": "chatcmpl-1",
            "object": "chat.completion",
            "created": 0,
            "model": body["model"],
            "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
        }
        data = json.dumps(answer).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: Any) -> None:
        return


def test_the_real_openai_sdk_is_used_for_answers_and_tool_calls() -> None:
    openai = pytest.importorskip("openai")
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeOpenAI)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        client = openai.OpenAI(base_url=f"http://127.0.0.1:{server.server_port}/v1", api_key="not-a-real-key")
        call = adapters.openai(client, "gpt-4o-mini", system="Route tickets.", temperature=0)
        assert call("card charged twice").answer == "billing"
        weather = call("what is the weather?")
        assert weather.answer == ""
        assert weather.tool_calls == [{"name": "get_weather", "arguments": '{"city": "Oslo"}'}]
    finally:
        server.shutdown()
        server.server_close()
