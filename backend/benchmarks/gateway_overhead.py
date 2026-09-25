"""
Gateway overhead benchmark (target: under 20 ms per call, excluding the model itself).

Runs sequential `GatewayService.complete` calls against `mock/echo`, whose own work is
effectively zero, on the running stack's Postgres and Valkey (`make up` first). Each call
goes through the full production path: profile lookup and decryption, parameter
filtering, the Valkey rate limiter, LiteLLM, cost, and the LLMCall insert. It reports
p50 / p95 / p99 of the whole call, the same numbers for a bare LiteLLM call to the same
mock (so LiteLLM's share is visible), and the machine it ran on. The benchmark's
throwaway user and workspace are deleted at the end.
"""

import asyncio
import os
import platform
import statistics
import subprocess
import time
import uuid
from collections.abc import Awaitable, Callable

import litellm
from sqlalchemy import delete

from app.core.config import Settings
from app.core.container import Container
from app.core.security import Principal
from app.core.throttle import FixedWindowLimiter
from app.modules.auth.models import Organization, User
from app.modules.auth.schemas import SignupRequest
from app.modules.auth.service import AuthService
from app.modules.gateway.dependencies import build_gateway
from app.modules.gateway.schemas import CallContext, CallPurpose, Message
from app.modules.gateway.service import configure_llm_runtime
from app.modules.projects.schemas import ProjectCreate
from app.modules.projects.service import ProjectService
from app.modules.registry.schemas import CredentialCreate
from app.modules.registry.service import RegistryService

CALLS = int(os.environ.get("BENCH_CALLS", "1000"))
WARMUP = 50
TARGET_MS = 20.0
MESSAGES = [
    Message(role="system", content="Classify the ticket."),
    Message(role="user", content="My card was charged twice"),
]


def percentiles(samples: list[float]) -> dict[str, float]:
    cuts = statistics.quantiles(samples, n=100)
    return {"p50": statistics.median(samples), "p95": cuts[94], "p99": cuts[98], "mean": statistics.fmean(samples)}


async def timed(call: Callable[[], Awaitable[object]], count: int) -> list[float]:
    samples = []
    for _ in range(count):
        began = time.perf_counter()
        await call()
        samples.append((time.perf_counter() - began) * 1000)
    return samples


def machine() -> str:
    cpu = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True).stdout.strip()
    system = f"{platform.system()} {platform.release()}"
    return f"{cpu or platform.processor()} · {os.cpu_count()} cores · {system} · Python {platform.python_version()}"


async def main() -> None:
    settings = Settings(
        _env_file="../.env",
        database_url=os.environ.get("VERANO_DATABASE_URL", "postgresql+asyncpg://verano:verano@localhost:5432/verano"),
        valkey_url=os.environ.get("VERANO_VALKEY_URL", "redis://localhost:6379/0"),
        mock_provider_enabled=True,
    )
    configure_llm_runtime(settings)
    container = Container.build(settings)
    email = f"bench-{uuid.uuid4().hex[:10]}@example.com"
    created: list[uuid.UUID] = []
    try:
        async with container.database.sessions() as db:
            auth = AuthService(
                db, container.passwords, container.access_tokens, settings, FixedWindowLimiter(container.valkey)
            )
            issued = await auth.signup(SignupRequest(email=email, password="benchmark-password", name="Bench"), "bench")
            principal = Principal(user_id=issued.body.user.id)
            project = await ProjectService(db, auth).create(principal, ProjectCreate(name="Gateway benchmark"))
            created.extend([project.organization_id, principal.user_id])
            registry = RegistryService(db, container)
            credential = await registry.add_credential(project, principal, CredentialCreate(provider="mock"))
            await db.commit()
            gateway = build_gateway(container, registry)
            context = CallContext(project_id=project.id)

            async def through_gateway() -> object:
                return await gateway.complete(
                    "echo", MESSAGES, {"temperature": 0}, credential.id, CallPurpose.TEST_RUN, context
                )

            async def bare_litellm() -> object:
                return await litellm.acompletion(
                    model="mock/echo", messages=[m.model_dump() for m in MESSAGES], num_retries=0, temperature=0
                )

            await timed(through_gateway, WARMUP)
            await timed(bare_litellm, WARMUP)
            gateway_ms = percentiles(await timed(through_gateway, CALLS))
            litellm_ms = percentiles(await timed(bare_litellm, CALLS))
        report(gateway_ms, litellm_ms)
    finally:
        await remove_benchmark_data(container, created)
        await container.close()


async def remove_benchmark_data(container: Container, created: list[uuid.UUID]) -> None:
    if not created:
        return
    organization_id, user_id = created
    async with container.database.sessions() as db:
        await db.execute(delete(Organization).where(Organization.id == organization_id))
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()


def report(gateway_ms: dict[str, float], litellm_ms: dict[str, float]) -> None:
    own = {key: gateway_ms[key] - litellm_ms[key] for key in gateway_ms}
    print(f"Gateway overhead benchmark · {CALLS} sequential calls on mock/echo · {machine()}")
    print(f"{'':28}{'p50':>8}{'p95':>8}{'p99':>8}{'mean':>8}   (ms)")
    for label, values in (
        ("Full gateway call", gateway_ms),
        ("  of which LiteLLM + mock", litellm_ms),
        ("  of which Verano's own work", own),
    ):
        print(f"{label:28}" + "".join(f"{values[k]:8.2f}" for k in ("p50", "p95", "p99", "mean")))
    verdict = "PASS" if gateway_ms["p95"] < TARGET_MS else "FAIL"
    print(f"Target: p95 of the full call under {TARGET_MS:.0f} ms → {verdict}")


if __name__ == "__main__":
    asyncio.run(main())
