# Verano

**Give it your API keys, a prompt and a few examples. Verano builds the evaluation,
benchmarks the models you choose, shows the quality / cost / speed tradeoffs, explains why
your prompt fails, and suggests better prompts, calling one better only when that is proven on
data it has never seen.**

Open source · Self-hostable · Apache 2.0

> **Status (2026-11-10):** the whole loop is built (keys → prompt → your data → test cases → run → results →
> improve), and so are the first four of the five planned phases: **proof and trust** (human labels and a judge
> checked against people), **real apps** (test your own app over HTTP), **the production loop** (serve the winning
> prompt, SDKs, a CI action, real traffic, teams) and **security, depth and hardening** (a security pack, Improve in
> several rounds, pause and resume, recovery from a dead worker). The open-source launch is not started.
> **Everything is tested on a mock provider, recorded responses and free models** (781 backend, 285 CLI, 28 SDK and 25 frontend
> tests pass, and 5 browser tests pass in Chromium, including every screen added since Phase 6); **nothing is proven on a
> paid model yet** because the spending cap is $0, and the browser tests have not been run in WebKit or Firefox. The CLI is
> not on PyPI. Evidence and gaps: the
> [Phase 8 and 9 checkpoint](docs/checkpoints/phase-8-9.md), the [Phase 6 and 7 checkpoint](docs/checkpoints/phase-6-7.md),
> the [pending checks](docs/PENDING_CHECKS.md) and the [backlog](docs/BACKLOG.md).

## Why it's different

- **Small input → full evaluation.** A prompt and a few examples are enough; Verano
  generates the test cases, expected outputs and evaluators, and you approve them.
- **Proven improvement.** A new prompt is built from one part of the data and confirmed on
  a held-back part it has never seen. If nothing beats your prompt, it says so.
  "Better" needs a clear difference on at least 15 held-back cases (a setting); otherwise it says *not
  proven* and shows the numbers.
- **A judge you choose, and can read.** The model that scores answers is picked on purpose (not
  the one that wrote the cases), its criteria are editable, every request it received can be read,
  and an answer it could not score is shown as unscored, never as a pass.
- **Consistency is a metric.** Each model runs each case several times, so you see how
  predictable it is, not just how good it was once.
- **Reproducible, and honest about it.** Every run records its exact configuration as a
  fingerprint, so two runs can be called *the same configuration*. You can re-run it, see
  whether the answers were the same (*stability*), and see the model version the provider
  reports. A fixed seed is shown as a setting, never as a guarantee.
- **Safe to run.** Every model call is shown with its cost first; generation and runs have a
  budget cap and a stop button; nothing paid starts without your say-so.
- **From your codebase.** The `verano` command-line tool looks for the prompts in your code
  (and says how sure it is), sets the project up, and can fail a pull request when quality drops.
- **A judge you can check.** People label answers (good, bad, unsure), blind review hides the judge's verdict, and
  Verano shows how often the judge agrees with them (raw agreement and Cohen's kappa), with a warning when it is low.
- **Your own app, not only a prompt.** Point Verano at an HTTP address and test the whole app: retrieved documents, tool
  calls and multi-turn conversations with a simulated user. Calls to internal addresses are refused unless you allow them.
- **The prompt reaches your app.** Production and staging labels, rollback, fetch by name with caching, Python and
  TypeScript libraries, a GitHub Action and an MCP server for AI agents.
- **Real traffic comes in.** Import traces (OpenTelemetry, HAR, Langfuse, Phoenix, LangSmith) or send spans to a thin
  OTLP receiver, turn them into draft test cases, and watch sampled scores and drift alerts. Personal data is removed first.
- **Teams.** Four roles, invites, sign-in with Google, Microsoft or any OIDC provider, one key store per workspace, a
  monthly spending limit and an audit log.
- **A small security pack.** Prompt injection, jailbreak, prompt leak, PII and harmful-content cases, written as ordinary
  approved cases, with a "harden" step that asks Improve for defensive instructions, a CI gate (`verano run --security`),
  and a **runtime screen** your app can call before and after a model call. The screen catches obvious cases only and is
  not a security boundary.
- **Free to try.** Runs on local models through Ollama, with no provider account and no API key.

## Quick start

Requires Docker. From a fresh clone:

```bash
make up
```

This creates `.env` with fresh secrets, builds the images, starts the stack and waits until
it is healthy. Open **http://localhost:8080** and create an account. Stop it with `make down` (your data is kept).
On a network that re-signs HTTPS and `make up` fails with a certificate error, see
[self-hosting](docs/guides/self-hosting.md#behind-a-company-firewall-that-re-signs-https).

### Set up on another machine

1. Install Docker (Desktop or Engine), [uv](https://docs.astral.sh/uv/) and `make`. Node is
   only needed for development outside Docker (`make install`).
2. Clone and start:

   ```bash
   git clone <your-repo-url> Verano
   cd Verano
   make up
   ```

3. Open **http://localhost:8080** and create an account.

What does not come with the clone:

- **`.env`** is git-ignored because it holds secrets. `make up` generates a new one. To reuse
  the same keys, copy the file over a secure channel, never by email or chat.
- **Your data** (accounts, projects, runs) lives in Docker volumes, so a new machine starts
  empty. To move it, take a `pg_dump` on the old machine and restore it on the new one.
- **Git-ignored local files** such as `goldenset.JSON`, `Daywise_logging/` and
  `backend/data/` must be copied by hand if you need them.
- **Local models:** install Ollama and run `make models`, or use `make up-local` to run
  Ollama in a container.

## Use it from your codebase

The `verano` command-line tool connects an existing application: it scans your code for prompts,
sets a project up in Verano, runs it on your examples, and can fail a pull request when quality
drops.

```bash
uv tool install ./cli      # or: pipx install ./cli
verano login && verano init && verano push && verano run
```

Beyond that it connects your own app (`verano app`), brings in traces (`verano traffic import`), runs the security
pack in the gate (`verano run --security`), gates on cost and speed as well as quality, and starts an MCP server for AI
agents (`verano mcp`, read-only by default). Python and TypeScript libraries to fetch a prompt by name live in
[`sdk/`](sdk/), and a GitHub Action in [`.github/actions/verano-run`](.github/actions/verano-run/) (built, not yet run in a real job).

See [`cli/README.md`](cli/README.md) for every command and the `verano.yaml` format, and
[`examples/support-triage`](examples/support-triage/) for a runnable example. The web app does
everything the command line does; use whichever you prefer.

## Integrations

<!-- integrations:start -->
Every integration below shows what has been checked, not what might work. Nothing is listed because it is only theoretically compatible (for example, through OpenTelemetry): a row needs the evidence for its status.

- **Validated:** checked against the real third-party tool or library, with the version and date recorded.
- **Sample-tested:** automated tests pass against stand-in objects or sample files we wrote.
- **Built:** the code exists; no automated test of this integration.
- **Planned:** not built.

Today: 4 validated · 10 sample-tested · 1 built · 10 planned.

### Native SDKs

| | Integration | Status | What it does and what shows it |
|---|---|---|---|
| <img src="docs/assets/logos/python.svg" alt="" width="20" height="20"> | **Python SDK** | Sample-tested | Fetch the prompt a label points at, with a saved copy for outages (`verano-sdk`, standard library only). [test_client.py](sdk/python/tests/test_client.py) (14 tests against a fake Verano). Not published to pypi. Next: Publish to PyPI, then run it against a real stack. |
| <img src="docs/assets/logos/typescript.svg" alt="" width="20" height="20"> | **TypeScript SDK** | Sample-tested | The same fetch, cache and fallback for Node, Bun and Deno (`@verano/sdk`, no dependencies). [client.test.ts](sdk/typescript/tests/client.test.ts) (14 tests against a fake fetch). Not published to npm. Next: Publish to npm, then run it against a real stack. |
| <kbd>CLI</kbd> | **Command line (`verano`)** | Sample-tested | Scan your code for prompts, push, run, gate a pull request, bring in traces, connect your app. [test_run.py](cli/tests/test_run.py) (against a fake platform). [test_init.py](cli/tests/test_init.py). Not published to pypi. Next: Publish to PyPI and install it on a clean machine. |
| <img src="docs/assets/logos/modelcontextprotocol.svg" alt="" width="20" height="20"> | **MCP server (`verano mcp`)** | Sample-tested | Lets an AI agent list projects, read results and, only with `--allow-write`, start runs and move labels. [test_integrations.py](cli/tests/test_integrations.py) (protocol, schemas and refusals; no real agent client). Next: Try it with a real MCP client (pending check 28). |

### Framework adapters

| | Integration | Status | What it does and what shows it |
|---|---|---|---|
| <img src="docs/assets/logos/pytest.svg" alt="" width="20" height="20"> | **pytest plugin** | Validated | `verano.test(case, fn)` checks your function in a normal pytest run and writes a JSON report. [test_integrations.py](cli/tests/test_integrations.py) (runs the real pytest in a subprocess with the plugin loaded). Checked with pytest 9.1.1 on 2026-11-10. |
| <img src="docs/assets/logos/langchain.svg" alt="" width="20" height="20"> | **LangChain adapter** | Validated | Makes a LangChain runnable or chain callable by `verano.test` and `verano.serve`. [test_adapters_real.py](cli/tests/test_adapters_real.py) (a real chain and runnable, no network). [test_integrations.py](cli/tests/test_integrations.py) (and against a stand-in runnable). [adapter-validation.md](docs/checkpoints/adapter-validation.md). Checked with langchain-core 1.7.7 on 2026-11-10. |
| <kbd>LI</kbd> | **LlamaIndex adapter** | Validated | Makes a LlamaIndex query engine callable, with the retrieved nodes as chunks. [test_adapters_real.py](cli/tests/test_adapters_real.py) (a real index and query engine with a mock model). [test_integrations.py](cli/tests/test_integrations.py) (and against a stand-in engine). [adapter-validation.md](docs/checkpoints/adapter-validation.md). Checked with llama-index-core 0.14.25 on 2026-11-10. |
| <kbd>OAI</kbd> | **OpenAI SDK adapter** | Validated | Uses an OpenAI client for chat completions and reports the tool calls a model makes. [test_adapters_real.py](cli/tests/test_adapters_real.py) (the real SDK against a local stand-in server). [test_integrations.py](cli/tests/test_integrations.py) (and against a stand-in client). [adapter-validation.md](docs/checkpoints/adapter-validation.md). Checked with openai 3.49.0 (against a local stand-in server, not the hosted API) on 2026-11-10. |

### Observability imports

| | Integration | Status | What it does and what shows it |
|---|---|---|---|
| <img src="docs/assets/logos/opentelemetry.svg" alt="" width="20" height="20"> | **OpenTelemetry (OTLP/HTTP JSON)** | Sample-tested | A thin receiver and a file import for GenAI spans, with personal data removed first. [test_receiver.py](backend/tests/integration/traffic/test_receiver.py) (spans we wrote). [test_adapters.py](backend/tests/unit/traffic/test_adapters.py). Next: Send spans from a real instrumented app (pending check 26) and import real exports (pending check 31). |
| <kbd>HAR</kbd> | **HAR files** | Sample-tested | Turns recorded browser calls to a model into traces. [test_adapters.py](backend/tests/unit/traffic/test_adapters.py) (a file we wrote). Next: Import a real export (pending check 31). |
| <kbd>LF</kbd> | **Langfuse export** | Sample-tested | Imports traces exported from Langfuse. [test_adapters.py](backend/tests/unit/traffic/test_adapters.py) (a file we wrote from memory of the format). Next: Import a real export (pending check 31). |
| <kbd>PX</kbd> | **Phoenix export** | Sample-tested | Imports traces exported from Arize Phoenix. [test_adapters.py](backend/tests/unit/traffic/test_adapters.py) (a file we wrote from memory of the format). Next: Import a real export (pending check 31). |
| <kbd>LS</kbd> | **LangSmith export** | Sample-tested | Imports runs exported from LangSmith. [test_adapters.py](backend/tests/unit/traffic/test_adapters.py) (a file we wrote from memory of the format). Next: Import a real export (pending check 31). |

### CI integrations

| | Integration | Status | What it does and what shows it |
|---|---|---|---|
| <img src="docs/assets/logos/githubactions.svg" alt="" width="20" height="20"> | **GitHub Action** | Built | Runs your prompt tests on a pull request, comments the results table and fails the job when a gate fails. Next: Run it in a real pull request (pending check 29). |
| <kbd>CI</kbd> | **Any CI (`verano run --ci`)** | Sample-tested | Exit code 2 when a quality, cost, speed or security gate fails; it never asks a question. [test_run.py](cli/tests/test_run.py) (against a fake platform). [test_security_gate.py](cli/tests/test_security_gate.py). Next: Run it in a real pipeline (pending check 13). |

### Planned

| | Integration | Status | What it does and what shows it |
|---|---|---|---|
| <img src="docs/assets/logos/go.svg" alt="" width="20" height="20"> | **Go SDK** (native sdks) | Planned | The same fetch, cache and fallback client. Next: Write it and run the shared contract tests against it. |
| <img src="docs/assets/logos/openjdk.svg" alt="" width="20" height="20"> | **Java SDK** (native sdks) | Planned | The same fetch, cache and fallback client. Next: Write it and run the shared contract tests against it. |
| <img src="docs/assets/logos/dotnet.svg" alt="" width="20" height="20"> | **C# SDK** (native sdks) | Planned | The same fetch, cache and fallback client. Next: Write it and run the shared contract tests against it. |
| <img src="docs/assets/logos/ruby.svg" alt="" width="20" height="20"> | **Ruby SDK** (native sdks) | Planned | The same fetch, cache and fallback client. Next: Write it and run the shared contract tests against it. |
| <img src="docs/assets/logos/jest.svg" alt="" width="20" height="20"> | **Jest plugin** (framework adapters) | Planned | What the pytest plugin does, for Jest. Next: Build it and run it in the real Jest. |
| <img src="docs/assets/logos/vitest.svg" alt="" width="20" height="20"> | **Vitest plugin** (framework adapters) | Planned | What the pytest plugin does, for Vitest. Next: Build it and run it in the real Vitest. |
| <kbd>OTel</kbd> | **OpenInference and OpenLLMetry instrumentation** (observability imports) | Planned | The auto-instrumentation libraries that make many frameworks emit OpenTelemetry spans. Next: Send real spans from each library to the receiver, and list a framework only once that has worked. |
| <img src="docs/assets/logos/gitlab.svg" alt="" width="20" height="20"> | **GitLab CI template** (ci integrations) | Planned | A ready-made job for `verano run --ci`. Next: Write the template and run it in a real GitLab pipeline. |
| <img src="docs/assets/logos/circleci.svg" alt="" width="20" height="20"> | **CircleCI template** (ci integrations) | Planned | A ready-made job for `verano run --ci`. Next: Write the template and run it in a real CircleCI pipeline. |
| <img src="docs/assets/logos/jenkins.svg" alt="" width="20" height="20"> | **Jenkins template** (ci integrations) | Planned | A ready-made pipeline step for `verano run --ci`. Next: Write the template and run it in a real Jenkins. |

Logos are the marks of their owners, shown only to say what works with Verano; it is not an endorsement. Sources and licences: [logo credits](docs/assets/logos/CREDITS.md).
<!-- integrations:end -->

## The loop, step by step

1. **Keys** — add a key per provider (OpenAI, Anthropic, Gemini, Groq, xAI, Mistral,
   Together, OpenRouter, or local Ollama). Verano checks it with a free request before saving
   it and shows the chat models with prices; tick the ones to compare. Checked against the live
   APIs so far: Gemini, OpenRouter and Ollama; the others follow their documentation and recorded
   responses.
2. **Prompt** — a system prompt, a user prompt with `{{ variables }}`, or both. A live check
   shows what each test case needs and whether it fits each model.
3. **Your data** (optional) — a golden set (inputs with answers), input files (inputs
   only) and reference documents; map the columns and see a row-numbered report.
4. **Test cases** — Verano describes the task for you to confirm, shows the cost (and asks
   when it is high), fills the gaps with generated cases, drafts answers, and you approve
   them. Generation has a budget cap and a stop button. Approval splits the cases 70/30 into
   "improve" and "held back".
5. **Run** — per model: runs, temperature and max tokens, and under *Advanced* a seed, top-p,
   stop sequences and (where the model accepts them) top-k and penalties. Temperature 0 and a
   fixed seed are filled in for you. Then the budget cap, the cost preview and live progress.
6. **Results** — quality, pass rate, consistency, **how alike the answers are across runs**,
   time and cost per model; every output side by side; CSV export. A **run configuration**
   panel shows what you set, what Verano locked and recorded, and what the provider
   controls, with a "same configuration" badge, **Re-run with same settings**, and a warning
   when the provider changed the model behind a name.
7. **Improve** — why cases fail, candidate prompts tested on the "improve" part (a quick check on a small fixed sample
   first, then a full test for the survivors), the best one checked on the held-back part, over several rounds if you
   ask, and "Accept as new version" only when it is proven better. Accepting can move a label such as `production`.

Alongside the steps: **Review** (label answers, blind), **Your apps** (connect an app over HTTP and test one case),
**Traffic** (imports, ingest tokens, scores, alerts), **Security** (the attack pack and its report), **Tokens** and a
**Workspace** page (members, invites, keys, spending limit, audit log). A run can be paused at the budget cap and resumed
with a higher cap, and a run whose worker died moves on by itself. Also a **Dashboard** (the latest run, pass rate across prompt versions, where
the money went), a **Logbook** (every answer and every model call, filterable, with CSV
export) and a **Prompt guide** (a prompting reference with copy-ready templates). Across all
projects, **Activity** shows spend, requests and tokens over time by model, key, project and
purpose, compared with the period before, and what was refused or failed.

To test local models, install [Ollama](https://ollama.com) (`brew install ollama`), run
`make models`, then add the "Ollama (local)" provider on the Keys screen. `make up-local`
runs Ollama in a container instead.

Running Verano on a server with HTTPS: see [self-hosting](docs/guides/self-hosting.md).

## Architecture

```text
Browser ─▶ Caddy (edge: real client IP, HTTPS) ─┬─ /api ─▶ FastAPI ─┬─ PostgreSQL
verano CLI, SDKs, your app's spans ───────────▶ │                   ├─ Valkey ◀─▶ Celery workers
                                                └─ UI ───▶ Next.js  └─ LLM Gateway ─▶ LiteLLM ─▶ providers
                                                                       └─ your app (HTTP, guarded) · code-check sandbox
```

A modular monolith: every feature module has the same shape (`router`, `service`, pure
`domain`, `repository`, `plugins`), and every LLM call, from test runs, generation, judges
or the assistant, goes through one gateway that filters parameters, rate-limits per key,
retries, prices and records it. The command-line tool is a separate package (`cli/`) that
uses only the public API, so it adds no second path to a model; calls to your own app go through a guarded client, and custom code checks run in a separate sandbox service. Details:
[architecture](docs/architecture.md) · [decisions](docs/adr/).

## Benchmarks

Measured, with the hardware stated ([all numbers](docs/benchmarks.md)):

| Target | Measured | Goal |
|---|---:|---:|
| Gateway overhead per call (p95, full path incl. DB record) | **5.6 ms** | < 20 ms |
| `verano push` of 100 test cases (upload, pair, approve) | **6.5 s** | none set |
| Fetch a prompt by name and label (median, 200 and 304) | **7.7 ms** | < 10 ms |
| Plan 50,000 calls | backlog | < 5 s |
| Results summary for 50,000 calls (p95) | backlog | < 300 ms |

Resilience (429 storms, bad keys, outages, forged headers, a dead worker, a failing provider): [resilience](docs/resilience.md). The 3,000-call load test was run (306 calls/s, 0 failed; [record](docs/checkpoints/load-test.md)).

## Extend it

Add an OpenAI-compatible provider with one YAML entry:

```yaml
  fireworks:
    display_name: Fireworks AI
    client: openai_compatible
    litellm_prefix: fireworks_ai
    base_url: https://api.fireworks.ai/inference/v1
    requires_key: true
    rate_limits: {rpm: 60, tpm: 500000}
```

Other providers take one small plugin class: [add a provider](docs/guides/add-a-provider.md).
Rule evaluators are one registered function each (`evaluation/plugins/rules.py`), and
the evaluators per task type are chosen in `evaluation/config/catalog.yaml`.

## Development

`make help` lists every command. `make ci` is the one gate (lint and types for the backend,
the CLI and the frontend, all tests, builds, images); `make e2e` runs the browser tests in
Chromium, WebKit and Firefox. See
[CONTRIBUTING.md](CONTRIBUTING.md) and [ENGINEERING_STANDARDS.md](docs/ENGINEERING_STANDARDS.md).

## Roadmap

Phases 6 to 9 are built and tested; Phase 10 is next. The earlier **pre-V1 plan** ([Part H](docs/DEVELOPMENT.md)) is
done except the checks that need paid models or people, which wait for a budget (decision 89) and for users after release.
The full plan is in the [backlog](docs/BACKLOG.md); what was built and what is left is in the checkpoints for
[Phases 6 and 7](docs/checkpoints/phase-6-7.md) and [Phases 8 and 9](docs/checkpoints/phase-8-9.md).

| Phase | Name | State |
|---|---|---|
| 6 | Proof and trust | **Built; real-model proof waiting for a budget.** Human labels and judge agreement, "Why this score", 27 rule checks, Python custom checks in a sandbox, a judge gallery, a judge cache |
| 7 | Real apps | **Built.** Connect your own app over HTTP (RAG, tool calls, conversations with a simulated user), several inputs per test case, several prompts per project, run parameters, `verano app` |
| 8 | The production loop | **Built and tested; screens opened and exercised in Chromium.** Prompt labels, SDKs, the GitHub Action, `verano mcp`, trace import and an OTLP receiver, online scoring and drift alerts, teams, an organization key store, a spending limit, an audit log. Not on PyPI; the Action has not run in a real job |
| 9 | Security, depth and hardening | **Built and tested.** A security pack and a runtime screen, Improve in several rounds, pause and resume, leases and a sweeper, a circuit breaker, live progress, a load test. "Harden" on a real model is untested, and the sandbox container can still reach the backend |
| 10 | Open-source launch | **Not started.** Public repository, website and documentation on free GitHub services, evidence page, outsider test, release gate |

What still needs a paid model (Improve, the judge, reproducibility) or people (the seven task types, the outsider test)
is listed in the [pending checks](docs/PENDING_CHECKS.md). Other projects are read for ideas only and nothing is copied
from them ([references](docs/REFERENCES.md)).

## License

[Apache 2.0](LICENSE)
