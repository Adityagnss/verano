# Contributing to Verano

Thanks for helping. Verano is built to be easy to extend and hard to break; the rules
below are what keep it that way.

## Set up

```bash
make env        # .env with fresh secrets (local HTTP mode)
make install    # uv sync --frozen + npm ci, exactly the locked versions
make hooks      # pre-commit checks on staged files
make up         # the whole stack at http://localhost:8080
```

No paid API key is needed: tests use a mock provider and recorded provider responses;
manual testing uses local Ollama models (`make models`).

## Before you open a pull request

- `make ci` passes. It is the one gate, locally and in any hosted CI.
- The change follows [ENGINEERING_STANDARDS.md](docs/ENGINEERING_STANDARDS.md): no
  hardcoded values, one header docstring per file and no line comments, registries
  instead of `if/elif` chains, files in their module's standard place.
- New behavior has one precise test named as a sentence; no redundant tests.
- Model changes come with an Alembic migration (`make migration name="..."`); API changes
  with a regenerated client (`make api-client`).
- A design decision comes with a short ADR in `docs/adr/`.
- Commits use conventional prefixes (`feat:`, `fix:`, `perf:`, `refactor:`, `docs:`).

## Common extensions

- [Add a provider](docs/guides/add-a-provider.md): usually one YAML entry.
- Add an evaluator: one plugin class plus one line in the evaluator catalog (the guide
  arrives with Phase 4).
