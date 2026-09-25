# Every common command (ENGINEERING_STANDARDS 11.2). Run `make help` for the list.
COMPOSE := docker compose
BACKEND := cd backend &&
LOCAL_OLLAMA := http://ollama:11434

.DEFAULT_GOAL := help
FRONTEND := cd frontend &&
OPENAPI := frontend/src/lib/api/openapi.json

.PHONY: help env install up up-local down logs migrate migration test test-all lint fmt models bench api-client e2e ci hooks

help: ## Show this list
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

env: ## Create .env from .env.example with generated secrets (never overwrites)
	python3 scripts/init_env.py

install: ## Install dependencies exactly as locked (uv sync --frozen, npm ci)
	$(BACKEND) uv sync --frozen
	$(FRONTEND) npm ci

up: ## Build and start the stack, waiting until every service is healthy
	$(COMPOSE) up -d --build --wait

up-local: ## Same as up, plus an Ollama container (clean-machine / demo path)
	OLLAMA_BASE_URL=$(LOCAL_OLLAMA) $(COMPOSE) --profile local up -d --build --wait

down: ## Stop every service (data volumes are kept)
	$(COMPOSE) --profile local down

logs: ## Follow service logs
	$(COMPOSE) logs -f

migrate: ## Apply database migrations (one-off job)
	$(COMPOSE) run --rm migrate

migration: ## Create a migration from model changes: make migration name="add x"
	$(BACKEND) uv run alembic revision --autogenerate -m "$(name)"

test: ## Run only the tests affected by your changes
	$(BACKEND) uv run pytest --testmon -q

test-all: ## Run the full test suite (phase checkpoints)
	$(BACKEND) uv run pytest -q

lint: ## Backend ruff + format check + mypy, frontend eslint + prettier + tsc
	$(BACKEND) uv run ruff check . && uv run ruff format --check . && uv run mypy app tests benchmarks
	$(FRONTEND) npm run lint && npm run typecheck

fmt: ## Auto-format and auto-fix
	$(BACKEND) uv run ruff check --fix . && uv run ruff format .
	$(FRONTEND) npm run format

models: ## Pull the local Ollama models (once)
	scripts/pull_models.sh

api-client: ## Regenerate the frontend API types from the backend OpenAPI schema
	$(BACKEND) PYTHONPATH=. uv run python ../scripts/export_openapi.py ../$(OPENAPI)
	$(FRONTEND) npx openapi-typescript src/lib/api/openapi.json -o src/lib/api/schema.d.ts

e2e: ## Browser tests (Chromium, WebKit, Firefox) against the stack, with the mock provider on
	VERANO_MOCK_PROVIDER_ENABLED=true $(COMPOSE) up -d --build --wait
	$(FRONTEND) npx playwright test

ci: ## The "CI green" gate: locked installs, lint, types, full tests (incl. migrations), builds, images
	$(BACKEND) uv sync --frozen
	$(FRONTEND) npm ci
	$(MAKE) lint
	$(BACKEND) uv run pytest -q
	$(FRONTEND) npm run build
	$(COMPOSE) build

hooks: ## Install the git pre-commit hook (ruff / prettier / eslint on staged files)
	git config core.hooksPath .githooks

bench: ## Measure performance targets (ENGINEERING_STANDARDS section 4)
	$(BACKEND) uv run python -m benchmarks.gateway_overhead
