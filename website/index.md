---
layout: home
title: Verano
titleTemplate: Test prompts and models on your own cases
editLink: false
lastUpdated: false
hero:
  name: Verano
  text: Test prompts and models on your own cases, and prove the better prompt.
  tagline: Open source and self-hosted. Verano shows the cost before it spends anything, and calls a new prompt better only when it wins on cases it never saw. Otherwise it says "Not proven".
  actions:
    - theme: brand
      text: Get started
      link: /get-started/quickstart
    - theme: alt
      text: Read the docs
      link: /get-started/
    - theme: alt
      text: GitHub
      link: https://github.com/Adityagnss/verano
features:
  - title: Cost first
    details: Every run, generation and judge call shows its estimated cost before it starts. Runs have a budget cap and a stop button, and nothing paid begins without your say-so.
    link: /guides/improve-a-prompt
    linkText: How Improve spends
  - title: Proof on held-back cases
    details: A new prompt is written from one part of your data and checked on a held-back part it has never seen. It is called better only with a clear difference on enough cases, otherwise Verano shows the numbers and says Not proven.
    link: /guides/improve-a-prompt
    linkText: Improve a prompt
  - title: No code needed
    details: The browser flow walks from your API keys and prompt to approved test cases, a run and a comparison of quality, cost and speed. Anything the web app does, the command line does too.
    link: /get-started/quickstart
    linkText: Quickstart
  - title: Write a prompt from your documents
    details: Add your documents, optionally say what the prompt should achieve, and press "Write it for me". You edit the draft before anything is saved.
    link: /guides/write-a-prompt-from-documents
    linkText: The guide
  - title: Test your own app over HTTP
    details: Point Verano at a chatbot, API or RAG app you already run. It sends each test case, reads the answer from the reply, and scores the answer, the retrieved text and the tool calls.
    link: /guides/test-your-own-app
    linkText: Connect an app
  - title: Live traffic
    details: Import traces from Langfuse, Phoenix, LangSmith, OpenTelemetry or a HAR file, turn them into draft test cases, and watch sampled scores and alerts. Personal data is removed first.
    link: /guides/live-traffic
    linkText: Bring in traffic
  - title: Safety checks
    details: Try common prompt-injection, jailbreak, prompt-leak, personal-data and harmful-content attacks on your prompt. You approve every attack case. A small set, not a security audit.
    link: /guides/safety-checks
    linkText: Check a prompt
  - title: A gate in your pull requests
    details: A GitHub Action runs your tests on every pull request, comments the results and fails the job when quality, cost or speed gets worse. A working demo is in the repository.
    link: /guides/use-in-ci
    linkText: Use it in CI
  - title: Use it from an AI agent
    details: "The verano mcp command starts an MCP server so an agent in your editor can list projects, run a test and read results. It is read-only until you start it with --allow-write, and --max-cost caps what it can spend."
    link: /guides/use-from-an-ai-agent
    linkText: Set up MCP
  - title: SDKs and framework adapters
    details: Python and TypeScript libraries fetch the prompt a label points at and keep working when Verano is down. A pytest plugin and LangChain, LlamaIndex and OpenAI adapters test your own code.
    link: /reference/integrations
    linkText: See every integration
---

<div class="home-wrap">

## The loop

<p class="lede">You bring a prompt and a key. Verano does the testing, and tells you what it could and could not show.</p>

<Diagram name="loop" />

<ol class="loop">
<li><strong>Prompt and key</strong>Your prompt, and a key for the models you want to compare, or a local model with no key.</li>
<li><strong>Approve cases</strong>Verano drafts test cases and checks from a few examples. You read and approve them.</li>
<li><strong>Run</strong>The cost is shown first. Each model answers each case more than once.</li>
<li><strong>Compare</strong>Quality, cost, speed and consistency side by side, with the reasons for each score.</li>
<li><strong>Improve</strong>Better prompts are written from the cases the prompt fails, in rounds.</li>
<li><strong>Check</strong>The best one is tested on held-back cases it never saw while it was written.</li>
<li class="end">
<div class="verdict ok"><strong>Proven</strong>A clear win on the held-back cases. You see the numbers and can save the prompt.</div>
<div class="verdict no"><strong>Not proven</strong>No clear win, or too few cases. Verano says so and shows the numbers, instead of calling it better.</div>
</li>
</ol>

## Get started

<p class="lede">Verano is self-hosted with Docker Compose. It is not on PyPI or npm and there is no hosted cloud yet, so you install from a clone of the repository.</p>

<div class="start-grid">
<div>

```bash
git clone https://github.com/Adityagnss/verano.git
cd verano
make env && make up
# then open http://localhost:8080
```

</div>
<div class="start-links">

- [Quickstart: your first project](/get-started/quickstart)
- [The command line](/reference/cli), from a clone with `uv tool install ./cli`
- [Self-hosting on a server with HTTPS](/self-hosting/)
- [Integrations, and what has been checked](/reference/integrations)
- [The code on GitHub](https://github.com/Adityagnss/verano)

</div>
</div>

<div class="honest">
<strong>Where it stands.</strong> The whole loop is built and runs. It has been tested on a built-in mock provider, recorded responses, free local models and, in small tests, real Claude models. Those tests could not yet prove an improved prompt, because the held-back set was too small (about 50 test cases are needed), so Verano said "Not proven". Everything on this site describes what is in the repository today.
</div>

<div class="author">
<p class="author-line">Open sourced by <strong>adityagnss</strong></p>
<p class="author-links"><a href="https://github.com/Adityagnss" target="_blank" rel="noopener">GitHub</a><a href="https://www.linkedin.com/in/adityagnss/" target="_blank" rel="noopener">LinkedIn</a><a href="https://github.com/Adityagnss/verano" target="_blank" rel="noopener">Star the project</a></p>
</div>

</div>
