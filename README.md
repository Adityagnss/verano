# Verano

**Give it your API keys, a prompt and a few examples. Verano builds the evaluation,
benchmarks the models you choose, shows the quality / cost / speed tradeoffs, explains why
your prompt fails, and gives you a better prompt that is proven on data it has never seen.**

Open source · Self-hostable · Apache 2.0

> **Status (2026-10-05):** the **whole loop is built** (keys → prompt → your data → test
> cases → run → results → improve) and was tested end to end in the browser on the mock
> provider. Since then the **pre-V1 plan** added three things: generation safety (stop button,
> budget cap, cost confirmation), **reproducibility** (settings, a configuration fingerprint,
> re-runs, stability, the model version a provider reports) and the **`verano` command-line
> tool** that sets a project up from existing code. Next: judge model choice and significance
> labels, then the checks that need a real model or a person. See the
> [plan](docs/DEVELOPMENT.md) (Part H), the [backlog](docs/BACKLOG.md) and the
> [pending checks](docs/PENDING_CHECKS.md); progress per step is in the
> [checkpoints](docs/checkpoints/).

## Why it's different

- **Small input → full evaluation.** A prompt and a few examples are enough; Verano
  generates the test cases, expected outputs and evaluators, and you approve them.
- **Proven improvement.** A new prompt is built from one part of the data and confirmed on
  a held-back part it has never seen. If nothing beats your prompt, it says so.
  (Significance labels are the next step; today it shows the plain difference.)
- **Consistency is a metric.** Each model runs each case several times, so you see how
  predictable it is, not just how good it was once.
- **Reproducible, and honest about it.** Every run records its exact configuration as a
  fingerprint, so two runs can be called *the same configuration*. You can re-run it, see
  whether the answers were the same (*stability*), and see the model version the provider
  reports. A fixed seed is shown as a setting, never as a guarantee.
- **Safe to run.** Every model call is shown with its cost first; generation and runs have a
  budget cap and a stop button; nothing paid starts without your say-so.
- **From your codebase.** The `verano` command-line tool finds the prompts in your code,
  sets the project up, and can fail a pull request when quality drops.
- **Free to try.** The whole loop runs on local models, with no account and no API key.

## Quick start

Requires Docker. From a fresh clone:

```bash
make up
```

This creates `.env` with fresh secrets, builds the images, starts the stack and waits until
it is healthy. Open **http://localhost:8080** and create an account.

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

See [`cli/README.md`](cli/README.md) for every command and the `verano.yaml` format, and
[`examples/support-triage`](examples/support-triage/) for a runnable example. The web app does
everything the command line does; use whichever you prefer.

## The loop, step by step

1. **Keys** — add a key per provider (OpenAI, Anthropic, Gemini, Groq, xAI, Mistral,
   Together, OpenRouter, or local Ollama). Verano checks it with a free model listing and
   shows the chat models with prices; tick the ones to compare.
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
7. **Improve** — why cases fail, 3 better prompts tested on the "improve" part, the best one
   checked on the held-back part, and "Accept as new version" when it really is better.

Alongside the steps: a **Dashboard** (the latest run, pass rate across prompt versions, where
the money went), a **Logbook** (every answer and every model call, filterable, with CSV
export) and a **Prompt guide** (a prompting reference with copy-ready templates).

To test local models, install [Ollama](https://ollama.com) (`brew install ollama`), run
`make models`, then add the "Ollama (local)" provider on the Keys screen. `make up-local`
runs Ollama in a container instead.

Running Verano on a server with HTTPS: see [self-hosting](docs/guides/self-hosting.md).

## Architecture

```text
Browser ─▶ Caddy (edge: real client IP, HTTPS) ─┬─ /api ─▶ FastAPI ─┬─ PostgreSQL
verano CLI ───────────────────────────────────▶ │                   ├─ Valkey ◀─▶ Celery workers
                                                └─ UI ───▶ Next.js  └─ LLM Gateway ─▶ LiteLLM ─▶ providers
```

A modular monolith: every feature module has the same shape (`router`, `service`, pure
`domain`, `repository`, `plugins`), and every LLM call, from test runs, generation, judges
or the assistant, goes through one gateway that filters parameters, rate-limits per key,
retries, prices and records it. The command-line tool is a separate package (`cli/`) that
uses only the public API, so it adds no second path to a model. Details:
[architecture](docs/architecture.md) · [decisions](docs/adr/).

## Benchmarks

Measured, with the hardware stated ([all numbers](docs/benchmarks.md)):

| Target | Measured | Goal |
|---|---:|---:|
| Gateway overhead per call (p95, full path incl. DB record) | **5.6 ms** | < 20 ms |
| `verano push` of 100 test cases (upload, pair, approve) | **6.5 s** | none set |
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

`make help` lists every command. `make ci` is the one gate (lint and types for the backend,
the CLI and the frontend, all tests, builds, images); `make e2e` runs the browser tests in
Chromium, WebKit and Firefox. See
[CONTRIBUTING.md](CONTRIBUTING.md) and [ENGINEERING_STANDARDS.md](docs/ENGINEERING_STANDARDS.md).

## Roadmap

The five phases are built (the last three at their base level; what was left for later is in
the [backlog](docs/BACKLOG.md)). The **pre-V1 plan** ([Part H](docs/DEVELOPMENT.md)) is
worked through in order:

1. Generation safety fixes — **done**
2. Reproducibility (settings, configuration fingerprint, re-run and stability, provider model
   id) — **done**
3. The `verano` CLI (`login`, `init`, `validate`, `push`, `run`, `status`, the CI gate) —
   **done**, not yet published to PyPI
4. Credibility items: judge model choice, "clear difference" labels, visible judge
   failures — **next** (planned in [Part H, H4](docs/DEVELOPMENT.md))
5. The [pending checks](docs/PENDING_CHECKS.md) with real models (planned in H5)

After V1: connecting an application that runs outside Verano (RAG, agents, tools), email
verification at sign-up, hosted CI. See the [plan](docs/DEVELOPMENT.md).

## License

[Apache 2.0](LICENSE)
