"""
Sandbox HTTP client.

HttpSandbox implements the Sandbox protocol by POSTing to the sandbox service (server.py).
Used by the API and workers when a sandbox URL is configured; an unreachable service becomes a
visible failure of that one check rather than an exception in the run.
"""

import httpx

from app.sandbox.contract import SandboxLimits, SandboxRequest, SandboxResult

NOT_REACHABLE = "The check sandbox is not reachable."
TIMEOUT_MARGIN_S = 5


class HttpSandbox:
    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")

    async def run(self, request: SandboxRequest, limits: SandboxLimits) -> SandboxResult:
        try:
            async with httpx.AsyncClient(timeout=limits.wall_s + TIMEOUT_MARGIN_S) as client:
                response = await client.post(f"{self._base_url}/run", json=request.model_dump(mode="json"))
                response.raise_for_status()
                return SandboxResult.model_validate(response.json())
        except (httpx.HTTPError, ValueError):
            return SandboxResult(ok=False, error=NOT_REACHABLE)
