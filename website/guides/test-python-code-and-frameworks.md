# Test your Python code and frameworks

If your app is a Python function, a LangChain chain, a LlamaIndex query engine or code that calls the OpenAI SDK, you can test it with ordinary `pytest`, or let Verano run its whole test set against it.

Install the command line with the extra you need:

```bash
pip install "verano[langchain]"     # or verano[llamaindex], verano[openai]
```

::: warning Not published yet
`verano` is not on PyPI yet. From a clone of the repository, use `uv tool install ./cli` or `pip install ./cli` instead.
:::

## Check a function in pytest

`verano.test` calls your function with the case's input, turns the reply (a string, a dict, or a framework result) into one answer, and fails the pytest test with a plain message if it does not match.

```python
import verano

def test_refund_time():
    verano.test(
        verano.Case(input="How long do refunds take?", contains=("5 business days",)),
        my_app,
    )
```

A case can check `expected` (equals), `contains`, `not_contains` or a `regex`. All the checks you give must hold. These checks are exact and run on your machine. Judging with a model happens in Verano, not here.

The plugin loads on its own. It prints a summary of every `verano.test` call, and `pytest --verano-report report.json` writes a JSON report.

## Use a framework object

Adapters make your object callable the way `verano.test` expects. They return the answer, the retrieved text and the tool calls.

```python
from verano.adapters import langchain, llamaindex, openai

fn = langchain(my_chain)                     # a LangChain runnable or chain
fn = llamaindex(my_query_engine)             # a LlamaIndex query engine
fn = openai(my_client, model="gpt-4o-mini")  # an OpenAI client
verano.test(verano.Case(input="...", contains=("...",)), fn)
```

The libraries are optional extras. Installing Verano never pulls them in.

## Let Verano test your function

`verano.serve` wraps your function in a small local web server, so Verano can run its whole test set against it, with the cost, scores and comparison you get for a prompt.

```python
with verano.serve(my_app) as server:
    print(server.url)   # register it with: verano app add
```

Then use [Test your own app](/guides/test-your-own-app) as usual. Verano's check for internal addresses applies, so allow `localhost` on the server (`VERANO_APP_ALLOWED_HOSTS`) when you try this on your own machine.

## What has been checked

The pytest plugin and the LangChain, LlamaIndex and OpenAI adapters were run against the real libraries. See the [integrations list](/reference/integrations) for the evidence behind each.
