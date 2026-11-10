# Contributing to Verano

Thanks for helping. Verano is built to be easy to extend and hard to break; the rules
below are what keep it that way.

## Set up

```bash
make env        # .env with fresh secrets (local HTTP mode)
make install    # uv sync --frozen (backend and cli) + npm ci, exactly the locked versions
make hooks      # pre-commit checks on staged files
make up         # the whole stack at http://localhost:8080
```

No paid API key is needed: tests use a mock provider and recorded provider responses;
manual testing uses local Ollama models (`make models`).

Where things live: `backend/` (API and workers), `frontend/` (the web app), `cli/` (the
`verano` command-line tool, its own package), `sdk/` (Python and TypeScript libraries), `website/` (this
project's website and docs), `examples/`.

## Before you open a pull request

- `make ci` passes. It is the one gate, locally and in any hosted CI, and it covers the
  backend, the CLI and the frontend.
- The change follows the code around it: no hardcoded values, one header docstring per file and no
  line comments, registries instead of `if/elif` chains, files in their module's standard place.
- New behavior has one precise test named as a sentence; no redundant tests. A test that
  starts a background job drains it before it ends.
- Model changes come with an Alembic migration (`make migration name="..."`); API changes
  with a regenerated client (`make api-client`).
- A change to how the CLI talks to the API is also run once against a real stack, because
  the fake servers in its tests are only our reading of the API.
- **Docs move with the code.** If a command, page or setting changed, update the guide for it in
  `website/content/` or the README, and run `make integrations` if you touched `integrations/registry.yaml`.
- Keep commits small, with a message that says what changed and why.

## Working on the CLI

```bash
cd cli
uv run pytest -q        # no network: the tests use fake servers
uv run ruff check . && uv run mypy src tests
uv run verano --help
```

`make lint` and `make ci` run these for you. See [`cli/README.md`](cli/README.md) for what the
tool does and [`examples/support-triage`](examples/support-triage/) for a runnable example.

## Common extensions

- [Add a provider](website/content/add-a-provider.md): usually one YAML entry.
- [Add a language to `verano init`](website/content/add-a-scanner-language.md): one table entry for
  a clue-based (Broad level) scan.
- Add an evaluator: one plugin class (`evaluation/plugins/`) plus one line in the evaluator
  catalog (`evaluation/config/catalog.yaml`); a written guide is still to do.
