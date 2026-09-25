# Verano

**Give it your API keys, a prompt and a few examples. Verano builds the evaluation,
benchmarks the models you choose, shows the quality / cost / speed tradeoffs, explains why
your prompt fails, and gives you a better prompt that is proven on data it has never seen.**

Open source · Self-hostable · Apache 2.0

> **Status:** Phase 1 of 5 is built: accounts, provider keys, model discovery and a
> production-grade LLM gateway, with a first UI (sign-in, projects, Keys step). One Phase 1
> check is still open: a real call to a local Ollama model. The
> evaluation builder, experiment engine, results and prompt improvement follow in Phases
> 2–5 ([plan](docs/DEVELOPMENT.md)). A demo GIF of the full loop arrives with Phase 5.

## Why it's different

- **Small input → full evaluation.** A prompt and a few examples are enough; Verano
  generates the test cases, expected outputs and evaluators, and you approve them.
- **Proven improvement.** A new prompt is built from one part of the data and confirmed on
  a held-back part with a significance check. If nothing beats your prompt, it says so.
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
| Plan 50,000 calls | Phase 3 | < 5 s |
| Results summary for 50,000 calls (p95) | Phase 4 | < 300 ms |

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
Evaluators work the same way (guide with Phase 4).

## Development

`make help` lists every command. `make ci` is the one gate (lint, types, all tests,
builds); `make e2e` runs the browser tests in Chromium, WebKit and Firefox. See
[CONTRIBUTING.md](CONTRIBUTING.md) and [ENGINEERING_STANDARDS.md](docs/ENGINEERING_STANDARDS.md).

## Roadmap

1. Foundation & model access (built; one manual check open)
2. Prompt & evaluation builder
3. Experiment engine
4. Evaluation & results
5. Prompt intelligence

Later: email verification at sign-up, hosted CI. See the [plan](docs/DEVELOPMENT.md).

## License

[Apache 2.0](LICENSE)
