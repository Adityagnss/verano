# Integrations

Generated from [`registry.yaml`](registry.yaml) by `make integrations`; do not edit by hand.

Every integration below shows what has been checked, not what might work. Nothing is listed because it is only theoretically compatible (for example, through OpenTelemetry): a row needs the evidence for its status.

- **Validated:** checked against the real third-party tool or library, with the version and date recorded.
- **Sample-tested:** automated tests pass against stand-in objects or sample files we wrote.
- **Built:** the code exists; no automated test of this integration.
- **Planned:** not built.

Today: 7 validated · 9 sample-tested · 1 built · 10 planned.

## Native SDKs

| | Integration | Status | What it does and what shows it |
|---|---|---|---|
| <img src="../../integrations/logos/python.svg" alt="" width="20" height="20"> | **Python SDK** | Sample-tested | Fetch the prompt a label points at, with a saved copy for outages (`verano-sdk`, standard library only). [test_client.py](../../sdk/python/tests/test_client.py) (14 tests against a fake Verano). [packaging.md](../../integrations/evidence/packaging.md) (builds and installs in a clean environment). Not published to pypi. Next: Publish to PyPI (you run it; commands in the packaging record), then run it against a real stack. |
| <img src="../../integrations/logos/typescript.svg" alt="" width="20" height="20"> | **TypeScript SDK** | Sample-tested | The same fetch, cache and fallback for Node, Bun and Deno (`@verano/sdk`, no dependencies). [client.test.ts](../../sdk/typescript/tests/client.test.ts) (14 tests against a fake fetch). [packaging.md](../../integrations/evidence/packaging.md) (builds and installs in a clean folder). Not published to npm. Next: Publish to npm (you run it; commands in the packaging record), then run it against a real stack. |
| <kbd>CLI</kbd> | **Command line (`verano`)** | Sample-tested | Scan your code for prompts, push, run, gate a pull request, bring in traces, connect your app. [test_run.py](../../cli/tests/test_run.py) (against a fake platform). [test_init.py](../../cli/tests/test_init.py). [packaging.md](../../integrations/evidence/packaging.md) (builds and installs in a clean environment). Not published to pypi. Next: Publish to PyPI (you run it), then install it on a clean machine with uvx. |
| <img src="../../integrations/logos/modelcontextprotocol.svg" alt="" width="20" height="20"> | **MCP server (`verano mcp`)** | Sample-tested | Lets an AI agent list projects, read results and, only with `--allow-write`, start runs and move labels. [test_integrations.py](../../cli/tests/test_integrations.py) (protocol, schemas and refusals; no real agent client). Next: Try it with a real MCP client (pending check 28). |

## Framework adapters

| | Integration | Status | What it does and what shows it |
|---|---|---|---|
| <img src="../../integrations/logos/pytest.svg" alt="" width="20" height="20"> | **pytest plugin** | Validated | `verano.test(case, fn)` checks your function in a normal pytest run and writes a JSON report. [test_integrations.py](../../cli/tests/test_integrations.py) (runs the real pytest in a subprocess with the plugin loaded). Checked on 2026-11-10 with pytest 9.1.1. |
| <img src="../../integrations/logos/langchain.svg" alt="" width="20" height="20"> | **LangChain adapter** | Validated | Makes a LangChain runnable or chain callable by `verano.test` and `verano.serve`. [test_adapters_real.py](../../cli/tests/test_adapters_real.py) (a real chain and runnable, no network). [test_integrations.py](../../cli/tests/test_integrations.py) (and against a stand-in runnable). [adapter-validation.md](../../integrations/evidence/adapter-validation.md). Checked on 2026-11-10 with langchain-core 1.7.7. |
| <kbd>LI</kbd> | **LlamaIndex adapter** | Validated | Makes a LlamaIndex query engine callable, with the retrieved nodes as chunks. [test_adapters_real.py](../../cli/tests/test_adapters_real.py) (a real index and query engine with a mock model). [test_integrations.py](../../cli/tests/test_integrations.py) (and against a stand-in engine). [adapter-validation.md](../../integrations/evidence/adapter-validation.md). Checked on 2026-11-10 with llama-index-core 0.14.25. |
| <kbd>OAI</kbd> | **OpenAI SDK adapter** | Validated | Uses an OpenAI client for chat completions and reports the tool calls a model makes. [test_adapters_real.py](../../cli/tests/test_adapters_real.py) (the real SDK against a local stand-in server). [test_integrations.py](../../cli/tests/test_integrations.py) (and against a stand-in client). [adapter-validation.md](../../integrations/evidence/adapter-validation.md). Checked on 2026-11-10 with openai 3.49.0 (against a local stand-in server, not the hosted API). |

## Observability imports

| | Integration | Status | What it does and what shows it |
|---|---|---|---|
| <img src="../../integrations/logos/opentelemetry.svg" alt="" width="20" height="20"> | **OpenTelemetry (OTLP/HTTP, protobuf and JSON)** | Validated | A thin receiver and a file import for GenAI spans, with personal data removed first. Takes the standard Python exporter's protobuf and JSON. [test_receiver.py](../../backend/tests/integration/traffic/test_receiver.py) (the exact bytes the real Python exporter sent). [test_adapters.py](../../backend/tests/unit/traffic/test_adapters.py) (and spans we wrote). [otel-validation.md](../../integrations/evidence/otel-validation.md). Checked on 2026-11-10 with opentelemetry-exporter-otlp-proto-http 1.45.2 (Python). The JavaScript exporter was not run. |
| <kbd>OI</kbd> | **OpenInference (OpenAI instrumentation)** | Validated | Spans from an OpenAI SDK call instrumented by OpenInference are read, with the question, answer, model and tokens. [test_receiver.py](../../backend/tests/integration/traffic/test_receiver.py) (bytes captured from the real library). [otel-validation.md](../../integrations/evidence/otel-validation.md). Checked on 2026-11-10 with openinference-instrumentation-openai 0.1.69 with openai 3.49.0. Only this instrumentation was tried. |
| <kbd>OLM</kbd> | **OpenLLMetry (OpenAI instrumentation)** | Validated | Spans from an OpenAI SDK call instrumented by OpenLLMetry are read, with the question, answer, model and tokens. [test_receiver.py](../../backend/tests/integration/traffic/test_receiver.py) (bytes captured from the real library). [otel-validation.md](../../integrations/evidence/otel-validation.md). Checked on 2026-11-10 with opentelemetry-instrumentation-openai 0.63.0 with openai 3.49.0. Only this instrumentation was tried. |
| <kbd>HAR</kbd> | **HAR files** | Sample-tested | Turns recorded browser calls to a model into traces. [test_adapters.py](../../backend/tests/unit/traffic/test_adapters.py) (a file we wrote). Next: Import a real export (pending check 31). |
| <kbd>LF</kbd> | **Langfuse export** | Sample-tested | Imports traces exported from Langfuse. [test_adapters.py](../../backend/tests/unit/traffic/test_adapters.py) (a file we wrote from memory of the format). Next: Import a real export (pending check 31). |
| <kbd>PX</kbd> | **Phoenix export** | Sample-tested | Imports traces exported from Arize Phoenix. [test_adapters.py](../../backend/tests/unit/traffic/test_adapters.py) (a file we wrote from memory of the format). Next: Import a real export (pending check 31). |
| <kbd>LS</kbd> | **LangSmith export** | Sample-tested | Imports runs exported from LangSmith. [test_adapters.py](../../backend/tests/unit/traffic/test_adapters.py) (a file we wrote from memory of the format). Next: Import a real export (pending check 31). |

## CI integrations

| | Integration | Status | What it does and what shows it |
|---|---|---|---|
| <img src="../../integrations/logos/githubactions.svg" alt="" width="20" height="20"> | **GitHub Action** | Built | Runs your prompt tests on a pull request, comments the results table and fails the job when a gate fails. Next: Run it in a real pull request (pending check 29). |
| <kbd>CI</kbd> | **Any CI (`verano run --ci`)** | Sample-tested | Exit code 2 when a quality, cost, speed or security gate fails; it never asks a question. [test_run.py](../../cli/tests/test_run.py) (against a fake platform). [test_security_gate.py](../../cli/tests/test_security_gate.py). Next: Run it in a real pipeline (pending check 13). |

## Planned

| | Integration | Status | What it does and what shows it |
|---|---|---|---|
| <img src="../../integrations/logos/go.svg" alt="" width="20" height="20"> | **Go SDK** (native sdks) | Planned | The same fetch, cache and fallback client. Next: Write it and run the shared contract tests against it. |
| <img src="../../integrations/logos/openjdk.svg" alt="" width="20" height="20"> | **Java SDK** (native sdks) | Planned | The same fetch, cache and fallback client. Next: Write it and run the shared contract tests against it. |
| <img src="../../integrations/logos/dotnet.svg" alt="" width="20" height="20"> | **C# SDK** (native sdks) | Planned | The same fetch, cache and fallback client. Next: Write it and run the shared contract tests against it. |
| <img src="../../integrations/logos/ruby.svg" alt="" width="20" height="20"> | **Ruby SDK** (native sdks) | Planned | The same fetch, cache and fallback client. Next: Write it and run the shared contract tests against it. |
| <img src="../../integrations/logos/jest.svg" alt="" width="20" height="20"> | **Jest plugin** (framework adapters) | Planned | What the pytest plugin does, for Jest. Next: Build it and run it in the real Jest. |
| <img src="../../integrations/logos/vitest.svg" alt="" width="20" height="20"> | **Vitest plugin** (framework adapters) | Planned | What the pytest plugin does, for Vitest. Next: Build it and run it in the real Vitest. |
| <kbd>OTel</kbd> | **Other OpenInference and OpenLLMetry instrumentations** (observability imports) | Planned | The instrumentations for LangChain, LlamaIndex, Anthropic and other frameworks, from either library. Next: Send real spans from each one to the receiver, and list a framework only once that has worked. |
| <img src="../../integrations/logos/gitlab.svg" alt="" width="20" height="20"> | **GitLab CI template** (ci integrations) | Planned | A ready-made job for `verano run --ci`. Next: Write the template and run it in a real GitLab pipeline. |
| <img src="../../integrations/logos/circleci.svg" alt="" width="20" height="20"> | **CircleCI template** (ci integrations) | Planned | A ready-made job for `verano run --ci`. Next: Write the template and run it in a real CircleCI pipeline. |
| <img src="../../integrations/logos/jenkins.svg" alt="" width="20" height="20"> | **Jenkins template** (ci integrations) | Planned | A ready-made pipeline step for `verano run --ci`. Next: Write the template and run it in a real Jenkins. |

Logos are the marks of their owners, shown only to say what works with Verano; it is not an endorsement. Sources and licences: [logo credits](../../integrations/logos/CREDITS.md).
