# Every common command (ENGINEERING_STANDARDS 11.2). Run `make help` for the list.
# Images are built on a dedicated buildx builder named `verano`, so Verano's build cache is
# kept apart from every other project on the machine and `make clean` can trim it safely.
# Cleanup only ever targets Verano's own leftovers; other projects' images, containers and
# volumes are never touched, and Verano's data volumes only by `make clean-all`.
export BUILDX_BUILDER := verano
BUILD_CACHE_LIMIT ?= 3gb
PROJECT_LABEL := label=com.docker.compose.project=verano
IMAGE_LABEL := label=dev.verano.image
COMPOSE := docker compose
BACKEND := cd backend &&
LOCAL_OLLAMA := http://ollama:11434

.DEFAULT_GOAL := help
FRONTEND := cd frontend &&
OPENAPI := frontend/src/lib/api/openapi.json

.PHONY: help env install builder up up-local down logs migrate migration test test-all lint fmt models bench api-client e2e ci hooks clean clean-all

help: ## Show this list
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

env: ## Create .env from .env.example with generated secrets (never overwrites)
	@python3 scripts/init_env.py

install: ## Install dependencies exactly as locked (uv sync --frozen, npm ci)
	$(BACKEND) uv sync --frozen
	$(FRONTEND) npm ci

builder: ## Create the dedicated `verano` image builder (once; later calls are no-ops)
	@docker buildx inspect verano >/dev/null 2>&1 || docker buildx create --name verano --driver docker-container --bootstrap >/dev/null

up: env builder ## Build and start the stack, waiting until every service is healthy (creates .env if missing)
	$(COMPOSE) up -d --build --wait
	@$(MAKE) --no-print-directory clean

up-local: env builder ## Same as up, plus an Ollama container (clean-machine / demo path)
	OLLAMA_BASE_URL=$(LOCAL_OLLAMA) $(COMPOSE) --profile local up -d --build --wait
	@$(MAKE) --no-print-directory clean

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
	$(BACKEND) uv run ruff check . ../scripts && uv run ruff format --check . ../scripts && uv run mypy app tests benchmarks ../scripts
	$(FRONTEND) npm run lint && npm run typecheck

fmt: ## Auto-format and auto-fix
	$(BACKEND) uv run ruff check --fix . ../scripts && uv run ruff format . ../scripts
	$(FRONTEND) npm run format

models: ## Pull the local Ollama models (once)
	scripts/pull_models.sh

api-client: ## Regenerate the frontend API types from the backend OpenAPI schema
	$(BACKEND) PYTHONPATH=. uv run python ../scripts/export_openapi.py ../$(OPENAPI)
	$(FRONTEND) npx openapi-typescript src/lib/api/openapi.json -o src/lib/api/schema.d.ts

e2e: env builder ## Browser tests (Chromium, WebKit, Firefox) against the stack, with the mock provider on
	VERANO_MOCK_PROVIDER_ENABLED=true $(COMPOSE) up -d --build --wait
	@$(MAKE) --no-print-directory clean
	$(FRONTEND) npx playwright test

ci: builder ## The "CI green" gate: locked installs, lint, types, full tests (incl. migrations), builds, images
	$(BACKEND) uv sync --frozen
	$(FRONTEND) npm ci
	$(MAKE) lint
	$(BACKEND) uv run pytest -q
	$(FRONTEND) npm run build
	$(COMPOSE) build
	@$(MAKE) --no-print-directory clean

clean: ## Remove Verano leftovers only (stopped containers, dangling images, cache over the limit); never volumes
	@docker container prune -f --filter $(PROJECT_LABEL) >/dev/null
	@docker container prune -f --filter label=org.testcontainers=true >/dev/null
	@docker image prune -f --filter $(IMAGE_LABEL) >/dev/null
	@docker image prune -f --filter $(PROJECT_LABEL) >/dev/null
	@docker buildx prune -f --builder verano --max-used-space $(BUILD_CACHE_LIMIT) >/dev/null 2>&1 || true
	@rm -rf frontend/test-results frontend/playwright-report
	@echo "Cleaned Verano leftovers (build cache kept under $(BUILD_CACHE_LIMIT); data volumes untouched)."

clean-all: ## Also delete Verano's images, build cache and DATA VOLUMES (database, Valkey, certificates); asks first
	@printf "This deletes Verano's database, Valkey data, certificates, images and build cache. Type 'yes' to continue: "; \
	read answer; [ "$$answer" = "yes" ] || { echo "Nothing deleted."; exit 1; }
	$(COMPOSE) --profile local down --volumes --rmi local --remove-orphans
	-docker buildx prune -f --all --builder verano
	@$(MAKE) --no-print-directory clean

hooks: ## Install the git pre-commit hook (ruff / prettier / eslint on staged files)
	git config core.hooksPath .githooks

bench: ## Measure performance targets (ENGINEERING_STANDARDS section 4)
	$(BACKEND) uv run python -m benchmarks.gateway_overhead
