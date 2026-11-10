# Architecture overview

How the parts of Verano connect when you run it with Docker Compose. It describes the system as built. For the reasoning behind a result, see [How it works](/how-it-works).

<Diagram name="architecture" caption="Everything enters through Caddy. Every model call goes through one gateway." />

## Reading the picture

- **Callers.** The browser, the `verano` command line and SDKs, and your app's traces all come in through Caddy. The command line uses only the public API ([API reference](/reference/api/)).
- **Caddy is the edge.** It terminates HTTPS, sees the real client IP, and is the only service that publishes a port. It sends the UI to the Next.js web app and `/api` to FastAPI.
- **One backend.** FastAPI and the Celery workers run the same code, organised by feature. PostgreSQL holds all data. Valkey holds queues, rate limits and progress.
- **One gateway for every model call.** Test runs, generation, judges and the Improve assistant all go through it. It rate-limits per key, retries, prices the call and records it, which is how cost can be shown before a run and added up after it. It reaches the providers through LiteLLM: OpenAI, Anthropic, Gemini, Groq, xAI, Mistral, Together, OpenRouter and local Ollama.
- **Your own app over HTTP** is called through a guarded client that refuses internal addresses unless the server owner allows the host ([guide](/guides/test-your-own-app)).
- **Custom code checks** run in a separate sandbox container.

Keys are encrypted with a master key you control (see [Self-hosting](/self-hosting/#secrets)).

## More pictures

- [How a result is decided](/how-it-works#how-a-result-is-decided): the held-back proof.
- [Use Verano in CI](/guides/use-in-ci): the pull request gate.
- [Live traffic](/guides/live-traffic): from traces to alerts.
- [Improve a prompt](/guides/improve-a-prompt): the proof, and the agent (MCP) path.
