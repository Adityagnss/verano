# Verano

**Give it your API keys, a prompt and a few examples. Verano builds the evaluation,
benchmarks the models you choose, shows the quality / cost / speed tradeoffs, explains why
your prompt fails, and gives you a better prompt that is proven on data it has never seen.**

Open source · Self-hostable · Apache 2.0

> **Status (2026-09-28):** the **base level of the whole loop is built**: keys → prompt →
> your data → test cases → run → results → improve, tested end to end in the browser on
> the mock provider. What still needs a real model or a person is listed in
> [pending checks](docs/PENDING_CHECKS.md); what was left for later rounds in the
> [backlog](docs/BACKLOG.md). Progress per phase: [checkpoints](docs/checkpoints/).

## Why it's different

- **Small input → full evaluation.** A prompt and a few examples are enough; Verano
  generates the test cases, expected outputs and evaluators, and you approve them.
- **Proven improvement.** A new prompt is built from one part of the data and confirmed on
  a held-back part it has never seen. If nothing beats your prompt, it says so.
  (Significance labels come in a later round; today it shows the plain difference.)
- **Consistency is a metric.** Each model runs each case several times, so you see how
  predictable it is, not just how good it was once.
- **Free to try.** The whole loop runs on local models, with no account and no API key.

## Quick start

Requires Docker. From a fresh clone:

```bash
make up
```

This creates `.env` with fresh secrets, builds the images, starts the stack and waits until
it is healthy. Open **http://localhost:8080** and create an account.

## The loop, step by step

1. **Keys** — add a key per provider (OpenAI, Anthropic, Gemini, Groq, xAI, Mistral,
   Together, OpenRouter, or local Ollama). Verano checks it with a free model listing and
   shows the chat models with prices; tick the ones to compare.
2. **Prompt** — a system prompt, a user prompt with `{{ variables }}`, or both. A live check
   shows what each test case needs and whether it fits each model.
3. **Your data** (optional) — a golden set (inputs with answers), input files (inputs
   only) and reference documents; map the columns and see a row-numbered report.
4. **Test cases** — Verano describes the task for you to confirm, shows the cost, fills the
   gaps with generated cases, drafts answers, and you approve them. Approval splits them
   70/30 into "improve" and "held back".
5. **Run** — runs per model, temperature and max tokens, a budget cap and the cost
   preview; then live progress per model.
6. **Results** — quality, pass rate, consistency, time and cost per model, every output
   side by side, CSV export.
7. **Improve** — why cases fail, 3 better prompts tested on the "improve" part, the best one
   checked on the held-back part, and "Accept as new version" when it really is better.

To test local models, install [Ollama](https://ollama.com) (`brew install ollama`), run
`make models`, then add the "Ollama (local)" provider on the Keys screen. `make up-local`
runs Ollama in a container instead.

Running Verano on a server with HTTPS: see [self-hosting](docs/guides/self-hosting.md).

## Architecture

```text
Browser ─▶ Caddy (edge: real client IP, HTTPS) ─┬─ /api ─▶ FastAPI ─┬─ PostgreSQL
                                                │                   ├─ Valkey ◀─▶ Celery workers
                                                └─ UI ───▶ Next.js  └─ LLM Gateway ─▶ LiteLLM ─▶ providers
```

A modular monolith: every feature module has the same shape (`router`, `service`, pure
`domain`, `repository`, `plugins`), and every LLM call, from test runs, generation, judges
or the assistant, goes through one gateway that filters parameters, rate-limits per key,
retries, prices and records it. Details: [architecture](docs/architecture.md) ·
[decisions](docs/adr/).

## Benchmarks

Measured, with the hardware stated ([all numbers](docs/benchmarks.md)):

| Target | Measured | Goal |
|---|---:|---:|
| Gateway overhead per call (p95, full path incl. DB record) | **5.6 ms** | < 20 ms |
| Plan 50,000 calls | backlog | < 5 s |
| Results summary for 50,000 calls (p95) | backlog | < 300 ms |

Resilience (429 storms, bad keys, outages, forged headers): [resilience](docs/resilience.md).

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

`make help` lists every command. `make ci` is the one gate (lint, types, all tests,
builds); `make e2e` runs the browser tests in Chromium, WebKit and Firefox. See
[CONTRIBUTING.md](CONTRIBUTING.md) and [ENGINEERING_STANDARDS.md](docs/ENGINEERING_STANDARDS.md).

## Roadmap

1. Foundation & model access — built
2. Prompt & evaluation builder — built
3. Experiment engine — base level built
4. Evaluation & results — base level built
5. Prompt intelligence — base level built

Next: the [pending checks](docs/PENDING_CHECKS.md) with real models, then the
[backlog](docs/BACKLOG.md). Later: email verification at sign-up, hosted CI. See the
[plan](docs/DEVELOPMENT.md).

## License

[Apache 2.0](LICENSE)
