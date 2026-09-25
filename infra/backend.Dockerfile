# Backend image: API, Celery worker and the one-off migrate job all run from it.
# Dependencies come only from the committed uv.lock (uv sync --frozen); the app runs as an
# unprivileged user. Build context: backend/.
FROM astral/uv:0.12.19 AS uv

FROM python:3.12.14-slim-bookworm AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /srv
COPY pyproject.toml uv.lock .python-version ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project

FROM python:3.12.14-slim-bookworm AS runtime
ENV PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 DEEPEVAL_TELEMETRY_OPT_OUT=YES \
    LITELLM_MODE=PRODUCTION LITELLM_LOCAL_MODEL_COST_MAP=True
RUN groupadd --system --gid 10001 verano && useradd --system --uid 10001 --gid verano --no-create-home verano
COPY --from=build /opt/venv /opt/venv
WORKDIR /srv
COPY --chown=verano:verano alembic.ini ./
COPY --chown=verano:verano migrations ./migrations
COPY --chown=verano:verano app ./app
USER verano
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=5 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"]
CMD ["uvicorn", "--factory", "app.main:create_app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers", "--timeout-graceful-shutdown", "30"]
