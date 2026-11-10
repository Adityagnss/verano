"""
3,000-call load test on the mock provider (backlog M8.5, scenario S9.8). The lead runs it; nothing here is paid.

Needs the running stack's Postgres and Valkey (`make up` first), like `gateway_overhead.py`. It measures, against the
targets in ENGINEERING_STANDARDS section 4 and 4b:

1. 3,000 gateway calls to `mock/echo`, 50 at a time: throughput, p50/p95/p99 of a call, failures, and the gateway's
   own overhead (the mock does no work, so the call time is overhead). Target: p95 under 20 ms per call when run one
   at a time (see gateway_overhead.py); under concurrency the number is queueing as well, so it is reported, not
   judged.
2. Planning 3,000 calls with `plan_matrix` (target: 50,000 under 5 s, so 3,000 under 0.3 s).
3. Pareto sorting of 8 candidates (target under 5 ms) and clustering of 1,000 failures (bounded memory, target in
   seconds) with the lexical embedder, with the peak memory of the clustering step.
4. The circuit breaker: failures opened it, the others kept going, a probe closed it (S9.9, in memory).

It prints a markdown table and, with `--write`, saves it to docs/checkpoints/load-test.md. A miss is written down
with the numbers, never hidden.
"""

import argparse
import asyncio
import os
import platform
import statistics
import subprocess
import time
import tracemalloc
import uuid
from datetime import date
from pathlib import Path

from sqlalchemy import delete

from app.core.config import Settings
from app.core.container import Container
from app.core.jobs import InlineJobQueue
from app.core.security import Principal
from app.core.throttle import FixedWindowLimiter
from app.modules.assistant.clustering import OnlineClusterer
from app.modules.assistant.search import Point, pick_winner
from app.modules.auth.models import Organization, User
from app.modules.auth.schemas import SignupRequest
from app.modules.auth.service import AuthService
from app.modules.engine.domain import plan_matrix
from app.modules.gateway.breaker import CircuitBreaker, CircuitState
from app.modules.gateway.dependencies import build_gateway
from app.modules.gateway.schemas import CallContext, CallPurpose, Message
from app.modules.gateway.service import configure_llm_runtime
from app.modules.generator.plugins.embedders import LexicalEmbedder
from app.modules.projects.schemas import ProjectCreate
from app.modules.projects.service import ProjectService
from app.modules.registry.schemas import CredentialCreate
from app.modules.registry.service import RegistryService

CALLS = 3_000
CONCURRENCY = 50
FAILURES = 1_000
MESSAGES = [
    Message(role="system", content="Classify the ticket."),
    Message(role="user", content="My card was charged twice"),
]
OUTPUT = Path(__file__).parents[2] / "docs" / "checkpoints" / "load-test.md"


def machine() -> str:
    cpu = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True).stdout.strip()
    return f"{cpu or platform.processor()} · {os.cpu_count()} cores · {platform.system()} {platform.release()} · Python {platform.python_version()}"  # noqa: E501


async def gateway_load(container: Container, settings: Settings) -> tuple[list[float], int, float]:
    email = f"load-{uuid.uuid4().hex[:10]}@example.com"
    organization_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None
    try:
        async with container.database.sessions() as db:
            auth = AuthService(
                db, container.passwords, container.access_tokens, settings, FixedWindowLimiter(container.valkey)
            )
            issued = await auth.signup(SignupRequest(email=email, password="benchmark-password", name="Load"), "load")
            principal = Principal(user_id=issued.body.user.id)
            project = await ProjectService(db, auth).create(principal, ProjectCreate(name="Load test"))
            organization_id, user_id = project.organization_id, principal.user_id
            registry = RegistryService(db, container)
            credential = await registry.add_credential(project, principal, CredentialCreate(provider="mock"))
            await db.commit()
            gateway = build_gateway(container, registry)
            # as in a run: the target is resolved once and committed, then every call records itself in its own
            # transaction (ADR 0011); sharing this session between 50 calls at once would not be a fair test
            target = await registry.call_target(project.id, credential.id, "echo")
            context = CallContext(project_id=project.id)
            limit = asyncio.Semaphore(CONCURRENCY)
            samples: list[float] = []
            failed = 0
            reasons: dict[str, int] = {}

            async def one() -> None:
                nonlocal failed
                async with limit:
                    began = time.perf_counter()
                    try:
                        await gateway.complete_target(
                            target, MESSAGES, {"temperature": 0}, CallPurpose.TEST_RUN, context
                        )
                        samples.append((time.perf_counter() - began) * 1000)
                    except Exception as error:
                        failed += 1
                        reason = f"{type(error).__name__}: {error}"[:160]
                        reasons[reason] = reasons.get(reason, 0) + 1

            started = time.perf_counter()
            await asyncio.gather(*(one() for _ in range(CALLS)))
            if reasons:
                print("Why calls failed:", sorted(reasons.items(), key=lambda item: -item[1])[:3])
            return samples, failed, time.perf_counter() - started
    finally:
        async with container.database.sessions() as db:
            if organization_id:
                await db.execute(delete(Organization).where(Organization.id == organization_id))
            if user_id:
                await db.execute(delete(User).where(User.id == user_id))
            await db.commit()


def timed_ms(work: object) -> float:
    began = time.perf_counter()
    assert callable(work)
    work()
    return (time.perf_counter() - began) * 1000


def breaker_check() -> bool:
    clock = [0.0]
    breaker = CircuitBreaker(5, 30.0, lambda: clock[0])
    for _ in range(5):
        breaker.failure("down")
    opened = breaker.state("down") is CircuitState.OPEN and not breaker.allow("down")
    others = breaker.allow("fine")
    clock[0] = 31.0
    probe = breaker.allow("down") and not breaker.allow("down")
    breaker.success("down")
    return opened and others and probe and breaker.state("down") is CircuitState.CLOSED


async def main(write: bool) -> None:
    settings = Settings(
        _env_file="../.env",
        database_url=os.environ.get("VERANO_DATABASE_URL", "postgresql+asyncpg://verano:verano@localhost:5432/verano"),
        valkey_url=os.environ.get("VERANO_VALKEY_URL", "redis://localhost:6379/0"),
        mock_provider_enabled=True,
    )
    configure_llm_runtime(settings)
    container = Container.build(settings, jobs=InlineJobQueue())
    try:
        samples, failed, seconds = await gateway_load(container, settings)
    finally:
        await container.close()
    cuts = statistics.quantiles(samples, n=100) if len(samples) > 100 else [0.0] * 99
    ids = [uuid.uuid4() for _ in range(100)]
    plan_ms = timed_ms(
        lambda: plan_matrix(uuid.uuid4(), ids, [(uuid.uuid4(), 6, {"temperature": 0}) for _ in range(5)])
    )
    points = [Point(str(i), 0.5 + i / 20, float(i % 3), 100 + i) for i in range(8)]
    pareto_ms = timed_ms(lambda: pick_winner(points))
    texts = [f"failure kind {i % 9} detail {i} " * 4 for i in range(FAILURES)]
    embedder = LexicalEmbedder()
    tracemalloc.start()
    began = time.perf_counter()
    clusterer = OnlineClusterer(24, 0.6, 5)
    for start in range(0, FAILURES, 200):
        for offset, vector in enumerate(embedder.embed(texts[start : start + 200])):
            clusterer.add(str(start + offset), vector, {"tag": "low_quality"}, None)
    cluster_s = time.perf_counter() - began
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    rows = [
        (
            "3,000 gateway calls, 50 at a time: throughput",
            f"{len(samples) / seconds:.0f} calls/s",
            "no target",
            "recorded",
        ),
        (
            "  call time p50 / p95 / p99 under load",
            f"{statistics.median(samples):.1f} / {cuts[94]:.1f} / {cuts[98]:.1f} ms",
            "p95 < 20 ms alone",
            "PASS" if cuts[94] < 20 else "MISS (queueing under load; see note)",
        ),
        ("  failed calls", f"{failed}", "0", "PASS" if failed == 0 else "MISS"),
        ("Plan 3,000 calls", f"{plan_ms:.1f} ms", "< 300 ms (50,000 < 5 s)", "PASS" if plan_ms < 300 else "MISS"),
        ("Pareto choice of 8 candidates", f"{pareto_ms:.3f} ms", "< 5 ms", "PASS" if pareto_ms < 5 else "MISS"),
        (
            f"Cluster {FAILURES:,} failures",
            f"{cluster_s:.2f} s, peak {peak / 1e6:.1f} MB",
            "bounded memory",
            "PASS" if len(clusterer.clusters()) <= 24 else "MISS",
        ),
        (
            "Circuit breaker opens, isolates, closes on a probe",
            "yes" if breaker_check() else "no",
            "S9.9",
            "PASS" if breaker_check() else "MISS",
        ),
    ]
    lines = [
        f"# Load test, 3,000 calls on the mock provider ({date.today().isoformat()})",
        "",
        f"Machine: {machine()}",
        "",
        "| What | Measured | Target (standards 4 and 4b) | Result |",
        "|---|---|---|---|",
        *[f"| {a} | {b} | {c} | {d} |" for a, b, c, d in rows],
        "",
        "Under concurrency a call's time includes waiting for a free connection, so its p95 is higher than the "
        "one-at-a-time overhead in `gateway_overhead.py`; the overhead target is judged by that script.",
    ]
    text = "\n".join(lines)
    print(text)
    if write:
        OUTPUT.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="save the table to docs/checkpoints/load-test.md")
    asyncio.run(main(parser.parse_args().write))
