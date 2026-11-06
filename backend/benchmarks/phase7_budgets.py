"""
Phase 7 latency budgets (ENGINEERING_STANDARDS section 4b) for calling the user's app and running custom checks.

The address check, reading an app's reply, rendering a request, one guarded call through an in-process fake app, and
starting a sandboxed check. Each line is the best of several repeats. No database and no real network are used.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable

import httpx

from app.core.egress import EgressPolicy, guarded_request, is_public_address
from app.modules.apps.mapping import ResponseMapping, apply_mapping, render_request
from app.sandbox.contract import SandboxLimits, SandboxRequest
from app.sandbox.runner import SubprocessSandbox

REPEATS = 5
CHECKS = 10_000
CALLS = 200
BODY = {
    "answer": "Refunds take 5 days.",
    "sources": [{"text": "Refund policy"}, {"text": "Shipping"}],
    "tool_calls": [{"name": "lookup", "arguments": {"topic": "refund"}}],
}
MAPPING = ResponseMapping("$.answer", "$.sources[*].text", "$.tool_calls", None)
POLICY = EgressPolicy(allowed_hosts=frozenset(), max_bytes=1_000_000, timeout_s=5.0, max_redirects=3)
LIMITS = SandboxLimits(wall_s=5.0, cpu_s=3, memory_mb=256, output_chars=300)


def best_ms(work: Callable[[], object]) -> float:
    work()
    best = float("inf")
    for _ in range(REPEATS):
        began = time.perf_counter()
        work()
        best = min(best, (time.perf_counter() - began) * 1000)
    return best


async def best_async_ms(work: Callable[[], Awaitable[object]]) -> float:
    await work()
    best = float("inf")
    for _ in range(REPEATS):
        began = time.perf_counter()
        await work()
        best = min(best, (time.perf_counter() - began) * 1000)
    return best


async def guarded_calls() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=BODY))
    for _ in range(CALLS):
        await guarded_request("POST", "http://8.8.8.8/ask", headers={}, body=b"{}", policy=POLICY, transport=transport)


async def one_sandboxed_check() -> None:
    request = SandboxRequest(code="def check(case):\n    return True\n", case={"output": "x", "inputs": {}})
    await SubprocessSandbox().run(request, LIMITS)


async def main() -> None:
    rows = [
        (
            "Address check, per call (over 10,000)",
            best_ms(lambda: [is_public_address("8.8.8.8") for _ in range(CHECKS)]) / CHECKS,
            1.0,
        ),
        (
            "Read an app's reply, per call (over 10,000)",
            best_ms(lambda: [apply_mapping(MAPPING, BODY) for _ in range(CHECKS)]) / CHECKS,
            5.0,
        ),
        (
            "Render a request, per call (over 10,000)",
            best_ms(lambda: [render_request('{"q": {{ q | tojson }}}', {"q": "hi"}) for _ in range(CHECKS)]) / CHECKS,
            5.0,
        ),
        ("Guarded app call overhead, per call (over 200)", await best_async_ms(guarded_calls) / CALLS, 30.0),
        ("Start one sandboxed check", await best_async_ms(one_sandboxed_check), 1000.0),
    ]
    print(f"{'Phase 7 latency budgets · best of 5':50}  measured ms  budget ms  result")
    for label, measured, budget in rows:
        print(f"{label:50}  {measured:11.3f}  {budget:9.1f}  {'PASS' if measured <= budget else 'MISS'}")


if __name__ == "__main__":
    asyncio.run(main())
