# Backend image: API, Celery worker and the one-off migrate job all run from it.
# Dependencies come only from the committed uv.lock (uv sync --frozen); the app runs as an
# unprivileged user. Build context: backend/.
# Size: the build stage strips debug symbols from native libraries (-58 MB) and drops
# LiteLLM's proxy admin web UI, static files the SDK never serves (-18 MB). Bytecode is kept
# compiled: removing it would save 99 MB but make every process start ~1.8 s slower.
# The runtime stage imports the app once at build time, so a bad strip can never ship.
FROM astral/uv:0.12.19 AS uv

FROM python:3.12.14-slim-bookworm AS build
RUN apt-get update && apt-get install -y --no-install-recommends binutils && rm -rf /var/lib/apt/lists/*
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /srv
COPY pyproject.toml uv.lock .python-version ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project
RUN find /opt/venv -name "*.so*" -type f -exec strip --strip-unneeded {} + \
 && rm -rf /opt/venv/lib/python3.12/site-packages/litellm/proxy/_experimental/out

FROM python:3.12.14-slim-bookworm AS runtime
ENV PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 DEEPEVAL_TELEMETRY_OPT_OUT=YES \
    LITELLM_MODE=PRODUCTION LITELLM_LOCAL_MODEL_COST_MAP=True
RUN groupadd --system --gid 10001 verano && useradd --system --uid 10001 --gid verano --no-create-home verano
COPY --from=build /opt/venv /opt/venv
WORKDIR /srv
COPY --chown=verano:verano alembic.ini ./
COPY --chown=verano:verano migrations ./migrations
COPY --chown=verano:verano app ./app
RUN python -c "import app.main, app.workers.tasks"
USER verano
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=5 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"]
CMD ["uvicorn", "--factory", "app.main:create_app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers", "--timeout-graceful-shutdown", "30"]
