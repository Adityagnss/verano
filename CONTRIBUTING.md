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
`verano` command-line tool, its own package), `docs/`, `examples/`. The layout and the rules
for each are in [ENGINEERING_STANDARDS.md](docs/ENGINEERING_STANDARDS.md), section 10.

## Before you open a pull request

- `make ci` passes. It is the one gate, locally and in any hosted CI, and it covers the
  backend, the CLI and the frontend.
- The change follows [ENGINEERING_STANDARDS.md](docs/ENGINEERING_STANDARDS.md): no
  hardcoded values, one header docstring per file and no line comments, registries
  instead of `if/elif` chains, files in their module's standard place.
- New behavior has one precise test named as a sentence; no redundant tests. A test that
  starts a background job drains it before it ends.
- Model changes come with an Alembic migration (`make migration name="..."`); API changes
  with a regenerated client (`make api-client`).
- A change to how the CLI talks to the API is also run once against a real stack, because
  the fake servers in its tests are only our reading of the API
  ([section 10.8](docs/ENGINEERING_STANDARDS.md)).
- **Docs move with the code.** Add a row to the decision log in
  [DEVELOPMENT.md](docs/DEVELOPMENT.md) (Part F), update the README status and
  [architecture](docs/architecture.md) if a capability, module, table or flow changed, strike
  what you built from the [backlog](docs/BACKLOG.md), and add a short ADR in `docs/adr/` when
  you make a design decision.
- Commits are one per step, named `<Phase or Part> · Step <n>: what changed`, for example
  `Part H · Step 3.4: verano run, status and the CI quality gate`.

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

- [Add a provider](docs/guides/add-a-provider.md): usually one YAML entry.
- [Add a language to `verano init`](docs/guides/add-a-scanner-language.md): one table entry for
  a clue-based (Broad level) scan.
- Add an evaluator: one plugin class (`evaluation/plugins/`) plus one line in the evaluator
  catalog (`evaluation/config/catalog.yaml`); a written guide is still to do.
