"""
FastAPI application factory.

`create_app` wires the process: structured logging, the LiteLLM runtime (including the
mock provider when enabled), the infrastructure container (DB engine, Valkey pool, HTTP
client, security primitives, storage, progress hub, job queue) created once in the
lifespan and closed on shutdown; tests pass their own job queue, the
single error-to-HTTP mapping, CORS for the frontend, and the /api/v1 routers.
Run with `uvicorn --factory app.main:create_app`.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.core.config import Settings, get_settings
from app.core.container import Container
from app.core.errors import install_error_handlers
from app.core.jobs import JobQueue
from app.core.logging import configure_logging
from app.modules.gateway.service import configure_llm_runtime
from app.workers.queue import CeleryJobQueue


def create_app(settings: Settings | None = None, jobs: JobQueue | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging(settings)
        configure_llm_runtime(settings)
        app.state.container = Container.build(settings, jobs=jobs or CeleryJobQueue())
        yield
        await app.state.container.close()

    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    install_error_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router, prefix=settings.api_prefix)

    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
