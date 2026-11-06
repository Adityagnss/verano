"""
Adapters that make an app built with a common library callable the way `verano.test` and `verano.serve` expect.

Each adapter takes your own object (a LangChain runnable, a LlamaIndex query engine, an OpenAI client) and returns
a function from the case's input to a `Reply` carrying the answer, the retrieved text and the tool calls. The
libraries are optional extras (`pip install "verano[langchain]"`) and are imported only when the adapter is built,
so installing Verano never pulls them in. Results are read by duck typing, so subclasses and newer versions work.
"""

import importlib
from collections.abc import Callable
from typing import Any

from verano.errors import CliError
from verano.testing import Reply, normalize

Adapter = Callable[[Any], Reply]


def _require(module: str, extra: str) -> None:
    try:
        importlib.import_module(module)
    except ImportError as error:
        raise CliError(
            f"This adapter needs the {module.split('.')[0]} package.", f'Install it with: pip install "verano[{extra}]"'
        ) from error


def langchain(runnable: Any, input_key: str | None = None) -> Adapter:
    """A LangChain runnable or chain. With `input_key`, the case's input is sent as {input_key: input}."""
    _require("langchain_core", "langchain")

    def call(case_input: Any) -> Reply:
        payload = {input_key: case_input} if input_key else case_input
        return normalize(runnable.invoke(payload))

    return call


def llamaindex(engine: Any) -> Adapter:
    """A LlamaIndex query engine (anything with `.query(text)`); the retrieved nodes become the chunks."""
    _require("llama_index.core", "llamaindex")

    def call(case_input: Any) -> Reply:
        result = engine.query(str(case_input))
        nodes = getattr(result, "source_nodes", None) or []
        chunks = [
            str(node.node.get_content() if hasattr(node, "node") else getattr(node, "text", node)) for node in nodes
        ]
        return Reply(str(getattr(result, "response", result)), chunks)

    return call


def openai(client: Any, model: str, system: str | None = None, **params: Any) -> Adapter:
    """An OpenAI client used for chat completions; tool calls the model makes are reported as tool calls."""
    _require("openai", "openai")

    def call(case_input: Any) -> Reply:
        messages = ([{"role": "system", "content": system}] if system else []) + [
            {"role": "user", "content": str(case_input)}
        ]
        message = client.chat.completions.create(model=model, messages=messages, **params).choices[0].message
        calls = [{"name": c.function.name, "arguments": c.function.arguments} for c in (message.tool_calls or [])]
        return Reply(message.content or "", [], calls)

    return call
