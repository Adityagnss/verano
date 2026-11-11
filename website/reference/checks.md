---
title: What Verano checks
description: All 37 checks in Verano, an open-source LLM evaluation tool. Prompt testing, scoring, model comparison, prompt optimization, cost control, red teaming, RAG and agent evaluation, live traffic monitoring and CI gates.
---

# What Verano checks

Verano is an open-source tool for **LLM evaluation**, **prompt testing** and **prompt optimization**. This page lists everything it does, in nine groups.


Jump to: [Access](#access) · [Getting started](#getting-started) · [Scoring](#scoring) · [Comparing](#comparing) · [Improving](#improving) · [Spend safety](#spend-safety) · [Production and apps](#production-and-apps) · [Security](#security) · [Developer workflow](#developer-workflow)

Search words people use for these: LLM evals, prompt evaluation, prompt regression testing, LLM-as-a-judge, RAG evaluation, agent evaluation, model comparison, prompt optimization, red teaming, prompt injection testing, LLM cost control, CI for prompts, LLM observability, self-hosted.


## Access

Where it runs and who can use it. 4 checks.

| Check | What Verano does |
|---|---|
| **Open-source license** | Apache 2.0. The whole repository. |
| **Free self-hosting** | Docker Compose with an HTTPS proxy. You run it yourself. |
| **Hosted cloud** | None. There is no hosted Verano today. |
| **Teams** | Invites, four roles, sign-in with Google, Microsoft or OIDC, a shared key store, an audit log and a monthly spending limit. |

## Getting started

From nothing to a first test. 5 checks.

| Check | What Verano does |
|---|---|
| **Whole loop without code** | Keys, prompt, test cases, run, results and a better prompt, all in the browser. |
| **Writes test cases for you** | Drafts inputs from your prompt, removes near-duplicates, and you approve each one. |
| **Writes expected answers** | A drafted answer or a rubric for every case. You approve them. |
| **Chooses the checks for you** | Picks checks to fit the type of task. |
| **Finds your prompts in your code** | <code>verano init</code> scans your files, says how sure it is, and never ticks a guess for you. |

## Scoring

How an answer gets a score. 5 checks.

| Check | What Verano does |
|---|---|
| **Rule and code checks** | More than 25 rule types, plus your own Python checks in a separate container with no internet. |
| **Ready-made LLM judges** | A judge gallery, RAG judges (faithfulness, context precision) and G-Eval style scoring. |
| **People label answers** | Labels, blind review and a review queue. |
| **Judge checked against people** | Shows how often the judge agrees with you, as raw agreement and Cohen's kappa. |
| **A failed judge is shown as unscored** | Never counted as a pass or a zero. It is left out of the numbers. |

## Comparing

Models and prompts side by side. 5 checks.

| Check | What Verano does |
|---|---|
| **Models side by side** | Nine providers plus local Ollama, on the same cases. |
| **Cost and speed per model** | Cost, time and tokens for each model. |
| **Repeat runs and consistency** | 1 to 5 runs per case, with consistency and same-text stability. |
| **Tests whether a difference is real** | A paired bootstrap with a 95% interval, so luck is not called a win. |
| **Reproducible runs** | A seed, a fingerprint of the settings, a Re-run with same settings button, and a warning when a provider changes the model behind a name. |

## Improving

Making the prompt better, with proof. 3 checks.

| Check | What Verano does |
|---|---|
| **Rewrites the prompt for you** | Groups failures by reason, then writes better prompts in rounds. Tested on small real-model runs so far. |
| **Confirms on cases it never saw** | Checks the best prompt on held-back cases with a statistical test, or says Not proven. |
| **A quick check before the full test** | A small fixed sample drops weak candidates first. Winners are chosen on quality against cost. |

## Spend safety

No surprise bills. 4 checks.

| Check | What Verano does |
|---|---|
| **Cost shown before running** | Every run, generation and judge call shows its estimate first. |
| **Budget cap and stop** | A cap on each run, a Stop button, and pause and resume. |
| **Pause at the cap and resume** | Raise the cap and carry on without repeating a call. Also after a worker stops. |
| **A monthly limit that refuses calls** | An admin sets a workspace limit. The next call is refused before it is made, and the run says why. |

## Production and apps

Your real app and real traffic. 6 checks.

| Check | What Verano does |
|---|---|
| **Traces from a live app** | An OpenTelemetry receiver (protobuf and JSON) and imports from Langfuse, Phoenix, LangSmith and HAR files. |
| **Scoring and alerts on live traffic** | Sampled scoring with the same checks, and alerts when quality stays lower for more than a day. |
| **Test cases from real traffic** | Real questions become draft cases you approve. Personal data is removed first. |
| **Serves the prompt to your app** | Labels such as production, rollback, fetch by name, token scopes, and Python and TypeScript libraries. |
| **Tests a whole app** | Point Verano at an HTTP address. It scores the answer, the retrieved text and the tool calls (RAG and agents). |
| **Multi-turn conversations** | Conversation cases, with a simulated user played by a judge model. |

## Security

Attacks and guardrails. 2 checks.

| Check | What Verano does |
|---|---|
| **Red teaming and guardrails** | Eight attack families mapped to the OWASP LLM Top 10: prompt injection, jailbreak, prompt leak, personal data and harmful content. A report, a CI gate and a runtime screen. A small set, not a security audit. |
| **Security failures feed the optimizer** | Harden turns failed attacks into defensive instructions and tests them on held-back attacks. Not yet tried on a paid model. |

## Developer workflow

Fit into how you build. 3 checks.

| Check | What Verano does |
|---|---|
| **Fails a pull request on a drop** | A command-line gate and a GitHub Action that fails the job when quality, cost or speed gets worse. |
| **SDKs and framework integrations** | Python and TypeScript libraries, a pytest plugin, and LangChain, LlamaIndex and OpenAI adapters. Not on PyPI or npm yet. |
| **Proven in real use** | Not yet. Verano is new, open source and built in the open. |

## Where it stands

- The whole loop is built and runs. It has been tested on a built-in mock provider, recorded responses, free local models and, in small tests, real Claude models.
- Those small tests could not yet prove an improved prompt, because the held-back set was too small (about 50 cases are needed), so Verano said "Not proven".
- See [Integrations](/reference/integrations) for what has been checked against real tools, and [User journeys](/get-started/user-journeys) for how people use it.
