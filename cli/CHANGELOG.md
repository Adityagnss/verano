# Changelog

All notable changes to the `verano` command-line tool. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Version policy

Verano uses [semantic versioning](https://semver.org/). Until 1.0, a change to the minor number
(0.2 to 0.3) may change a command or the shape of `verano.yaml`, and the changelog says how to adapt.
A patch number (0.2.0 to 0.2.1) only fixes things. The version lives in one place,
`src/verano/__init__.py`; `verano --version` prints it, and the release is tagged `cli-vX.Y.Z`.
The CLI and the server share the public API's versioning (`/api/v1`): a CLI works with any server
that serves the same API version.

## 0.2.0 (2026-11-10)

### Added

- `verano mcp`: a local MCP server (read-only unless started with `--allow-write`).
- `verano run --ci` gates on cost and speed (`max_cost_per_call`, `max_latency_ms`, `max_cost_increase`,
  `max_slowdown`), a pinned baseline run (`--baseline`, or `baseline:` in the gate) and `--markdown-file`
  for a pull-request comment. The official GitHub Action in `.github/actions/verano-run` uses these.
- `verano.test(case, fn)`, `verano.serve(fn)`, the pytest plugin and adapters for LangChain, LlamaIndex and
  the OpenAI SDK (optional extras: `verano[langchain]`, `verano[llamaindex]`, `verano[openai]`).
- `verano token create --read-only --project NAME`; `token list` shows each token's scope.
- `verano push --label NAME` points a prompt label at the pushed version; push replaces a provider key that was
  rotated in the environment and names prompts that were removed from the file.
- `verano init` also reads prompts kept in `.txt`, `.md`, `.jinja` and `.yaml` files, and writes the tools and
  retrieval it found as notes in `verano.yaml` (`retrieval:` and `tools:` are accepted keys).

## 0.1.0

First version: `login`, `init`, `validate`, `push`, `run`, `status`, `token`, `app`.
