"""
Sandbox HTTP service.

A tiny FastAPI app run inside the separate no-network sandbox container: POST /run executes one
check through SubprocessSandbox, GET /health reports liveness. A semaphore caps concurrent runs.
Limits and concurrency come from VERANO_SANDBOX_* environment variables read in main().
Called over the private network by HttpSandbox (client.py).
"""

import asyncio
import os

import uvicorn
from fastapi import FastAPI

from app.sandbox.contract import SandboxLimits, SandboxRequest, SandboxResult
from app.sandbox.runner import Sandbox, SubprocessSandbox

HOST = "0.0.0.0"
PORT = 8099
DEFAULT_CONCURRENCY = 8


def create_app(sandbox: Sandbox, limits: SandboxLimits, concurrency: int = DEFAULT_CONCURRENCY) -> FastAPI:
    app = FastAPI(title="Verano check sandbox")
    gate = asyncio.Semaphore(concurrency)

    @app.post("/run")
    async def run(request: SandboxRequest) -> SandboxResult:
        async with gate:
            return await sandbox.run(request, limits)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


def limits_from_env() -> SandboxLimits:
    return SandboxLimits(
        wall_s=float(os.environ["VERANO_SANDBOX_WALL_S"]),
        cpu_s=int(os.environ["VERANO_SANDBOX_CPU_S"]),
        memory_mb=int(os.environ["VERANO_SANDBOX_MEMORY_MB"]),
        output_chars=int(os.environ["VERANO_SANDBOX_OUTPUT_CHARS"]),
    )


def main() -> None:
    concurrency = int(os.environ.get("VERANO_SANDBOX_CONCURRENCY", DEFAULT_CONCURRENCY))
    app = create_app(SubprocessSandbox(), limits_from_env(), concurrency)
    uvicorn.run(app, host=HOST, port=PORT)


if __name__ == "__main__":
    main()
