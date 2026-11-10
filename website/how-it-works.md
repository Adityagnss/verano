# How it works

A short overview of the parts. It describes the system as built.

```text
Browser ─▶ Caddy (the single entry point) ─┬─ /api ─▶ FastAPI ─┬─ PostgreSQL
verano CLI, libraries, your app's spans ──▶ │                   ├─ Valkey ◀─▶ Celery workers
                                            └─ UI ───▶ Next.js └─ LLM gateway ─▶ LiteLLM ─▶ providers
                                                                   └─ your app (HTTP, guarded) · code-check sandbox
```

- **One backend, organised by feature.** A modular monolith: one FastAPI service and Celery workers running the same code, a Next.js web app, PostgreSQL for all data, Valkey for queues, rate limits and progress. Caddy is the only service that publishes a port.
- **One path to every model.** Test runs, generation, judges and the Improve assistant all call models through one gateway. It filters parameters a model does not accept, rate-limits per key, retries, prices the call and records it. That is how cost can be shown before a run and added up after it.
- **Providers through LiteLLM.** OpenAI, Anthropic, Gemini, Groq, xAI, Mistral, Together, OpenRouter and Ollama, plus a built-in mock provider for tests. Adding an OpenAI-compatible provider is one YAML entry ([guide](/guides/add-a-provider)).
- **The command line uses only the public API.** It adds no second path to a model ([API reference](/reference/api/)).
- **Your own app is called through a guarded client.** It refuses internal addresses unless the server owner allows the host ([guide](/guides/test-your-own-app)).
- **Custom code checks run in a separate sandbox service.**
- **Runs survive trouble.** A run that loses its worker is picked up again, can be paused and resumed, and stops at its budget.
- **Keys are encrypted** with a master key you control (see [Self-hosting](/self-hosting/#secrets)).

## How a result is decided

1. Your approved cases are split about 70/30 into a part used to write improvements and a held-back part.
2. Answers are scored by rule checks, optionally code checks, and a judge model you choose.
3. Improve writes candidate prompts from the first part, then tests the best on the held-back part.
4. A prompt is called better only with a clear difference on enough held-back cases. Otherwise the result is *Not proven*.

The source is on [GitHub](https://github.com/Adityagnss/verano).
