import type { DiagramSpec } from "./layout"

export const specs: Record<string, DiagramSpec> = {
  loop: {
    alt: "The Verano loop. Your prompt and key lead to approved test cases, then a run with the cost shown first, then a comparison, then Improve, then a check on held-back cases. The end is either Proven, a clear win, or Not proven, no clear win or too few cases.",
    flow: "h",
    layers: [
      [{ id: "p", label: "Prompt and key", sub: "Or a local model with no key", kind: "edge" }],
      [{ id: "a", label: "Approve cases", sub: "You read and approve them" }],
      [{ id: "r", label: "Run", sub: "The cost is shown first" }],
      [{ id: "c", label: "Compare", sub: "Quality, cost, speed, consistency" }],
      [{ id: "i", label: "Improve", sub: "Written from the cases that fail, in rounds" }],
      [{ id: "k", label: "Check", sub: "On held-back cases it never saw", kind: "core" }],
      [
        { id: "ok", label: "Proven", sub: "A clear win on held-back cases", kind: "ok" },
        { id: "no", label: "Not proven", sub: "No clear win, or too few cases", kind: "warn" },
      ],
    ],
    edges: [
      { from: "p", to: "a" },
      { from: "a", to: "r" },
      { from: "r", to: "c" },
      { from: "c", to: "i" },
      { from: "i", to: "k" },
      { from: "k", to: "ok" },
      { from: "k", to: "no" },
    ],
  },
  architecture: {
    alt: "Architecture. A browser, the verano command line and SDKs, and your app's traces all enter through Caddy, the edge that does HTTPS and the real client IP. Caddy sends the UI to the Next.js web app and the API to FastAPI. FastAPI uses PostgreSQL and Valkey. Celery workers take work from Valkey, store results in PostgreSQL, and call three things: the one model gateway (rate limits, retries, cost, recording) which reaches the providers through LiteLLM, your own app over HTTP through a guarded client, and the code-check sandbox, a separate container.",
    flow: "rows",
    layers: [
      [
        { id: "br", label: "Browser", sub: "The web app", kind: "muted" },
        { id: "cli", label: "verano command line and SDKs", sub: "Public API only", kind: "muted" },
        { id: "tr", label: "Your app's traces", sub: "OpenTelemetry spans", kind: "muted" },
      ],
      [{ id: "caddy", label: "Caddy (edge)", sub: "HTTPS, real client IP. The only published port", kind: "edge" }],
      [
        { id: "web", label: "Web app (Next.js)", sub: "The UI" },
        { id: "api", label: "API (FastAPI)", sub: "One backend, organised by feature" },
      ],
      [
        { id: "valkey", label: "Valkey", sub: "Queues, rate limits, progress" },
        { id: "pg", label: "PostgreSQL", sub: "All data" },
      ],
      [{ id: "wk", label: "Celery workers", sub: "Run the tests, same code as the API" }],
      [
        { id: "sb", label: "Code-check sandbox", sub: "A separate container", kind: "warn" },
        { id: "gw", label: "ONE model gateway", sub: "Rate limits, retries, cost, recording", kind: "core" },
        { id: "app", label: "Your own app over HTTP", sub: "Guarded client", kind: "warn" },
      ],
      [{ id: "pr", label: "Providers, through LiteLLM", sub: "OpenAI, Anthropic, Gemini, Groq, xAI, Mistral, Together, OpenRouter, local Ollama", kind: "muted" }],
    ],
    edges: [
      { from: "br", to: "caddy" },
      { from: "cli", to: "caddy" },
      { from: "tr", to: "caddy" },
      { from: "caddy", to: "web", label: "UI" },
      { from: "caddy", to: "api", label: "/api" },
      { from: "api", to: "valkey" },
      { from: "api", to: "pg" },
      { from: "valkey", to: "wk" },
      { from: "wk", to: "pg" },
      { from: "wk", to: "sb" },
      { from: "wk", to: "gw" },
      { from: "wk", to: "app" },
      { from: "gw", to: "pr" },
    ],
  },
  proof: {
    alt: "Proof on held-back cases. Approved cases are split about 70 percent to improve and 30 percent held back. Candidate prompts are written and tested on the 70 percent. The best candidate is then checked on the held-back 30 percent. The result is Proven better, or Not proven, which also happens when there are too few held-back cases; the default minimum is 15.",
    flow: "h",
    layers: [
      [{ id: "all", label: "Approved cases", sub: "Split about 70 / 30", kind: "edge" }],
      [
        { id: "imp", label: "70% to improve", sub: "Used to write better prompts" },
        { id: "held", label: "30% held back", sub: "Never shown to the writer", kind: "core" },
      ],
      [{ id: "cand", label: "Candidates", sub: "Written and tested on the 70%" }],
      [{ id: "best", label: "Best one checked", sub: "On the held-back cases", kind: "core" }],
      [
        { id: "ok", label: "Proven better", sub: "A clear gap, on enough cases", kind: "ok" },
        { id: "no", label: "Not proven", sub: "Needs enough held-back cases, default 15", kind: "warn" },
      ],
    ],
    edges: [
      { from: "all", to: "imp" },
      { from: "all", to: "held" },
      { from: "imp", to: "cand" },
      { from: "cand", to: "best" },
      { from: "held", to: "best" },
      { from: "best", to: "ok" },
      { from: "best", to: "no" },
    ],
  },
  ci: {
    alt: "The CI gate. A pull request starts a GitHub Action, which runs verano run --ci. The quality, cost and speed gate decides: it passes, or it fails with exit code 2 and a results table.",
    flow: "h",
    layers: [
      [{ id: "pr", label: "Pull request", kind: "edge" }],
      [{ id: "ga", label: "GitHub Action", sub: "verano-run" }],
      [{ id: "run", label: "verano run --ci", sub: "Runs your tests in Verano" }],
      [{ id: "gate", label: "Gate", sub: "Quality, cost, speed", kind: "core" }],
      [
        { id: "pass", label: "Pass", sub: "Exit code 0", kind: "ok" },
        { id: "fail", label: "Fail", sub: "Exit code 2 and a results table", kind: "warn" },
      ],
    ],
    edges: [
      { from: "pr", to: "ga" },
      { from: "ga", to: "run" },
      { from: "run", to: "gate" },
      { from: "gate", to: "pass" },
      { from: "gate", to: "fail" },
    ],
  },
  traffic: {
    alt: "Live traffic. Traces come in from OpenTelemetry, Langfuse, Phoenix, LangSmith or a HAR file. Personal data is removed. Then two things happen: draft test cases that you approve, and sampled live scores. Live scores feed alerts.",
    flow: "h",
    layers: [
      [{ id: "in", label: "Traces in", sub: "OpenTelemetry, Langfuse, Phoenix, LangSmith, HAR", kind: "edge" }],
      [{ id: "pii", label: "Personal data removed", sub: "Before anything is used" }],
      [
        { id: "draft", label: "Draft test cases", sub: "You approve them", kind: "core" },
        { id: "score", label: "Sampled live scores", sub: "Same checks as your tests" },
      ],
      [{ id: "alert", label: "Alerts", sub: "Slack, webhook, email", kind: "warn" }],
    ],
    edges: [
      { from: "in", to: "pii" },
      { from: "pii", to: "draft" },
      { from: "pii", to: "score" },
      { from: "score", to: "alert" },
    ],
  },
  mcp: {
    alt: "MCP. An AI agent talks to verano mcp over stdio, and verano mcp talks to the Verano API. It is read-only by default; the flags --allow-write and --max-cost allow changes and cap spending.",
    flow: "h",
    layers: [
      [{ id: "ag", label: "AI agent", sub: "An MCP client", kind: "edge" }],
      [{ id: "mcp", label: "verano mcp", sub: "stdio. Read-only by default; --allow-write, --max-cost", kind: "core" }],
      [{ id: "api", label: "Verano API", sub: "The public API" }],
    ],
    edges: [
      { from: "ag", to: "mcp", both: true },
      { from: "mcp", to: "api", both: true },
    ],
  },
}
