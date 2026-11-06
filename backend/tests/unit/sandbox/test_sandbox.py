"""The check sandbox (ADR 0019): a good check runs; loops, files, sockets and imports fail safely and do not stop
other checks.
"""

import asyncio

import pytest

from app.sandbox.contract import SandboxLimits, SandboxRequest, normalise_result
from app.sandbox.runner import SubprocessSandbox

LIMITS = SandboxLimits(wall_s=5.0, cpu_s=3, memory_mb=256, output_chars=300)
CASE = {"inputs": {"ticket": "hi"}, "output": "Dear Sam, thanks", "expected": None, "rubric": None}


async def run(code: str, limits: SandboxLimits = LIMITS):  # type: ignore[no-untyped-def]
    return await SubprocessSandbox().run(SandboxRequest(code=code, case=CASE), limits)


async def test_a_good_check_returns_its_score_and_reason() -> None:
    result = await run("def check(case):\n    return (0.7, 'looks fine ' + case['output'][:4])\n")
    assert (result.ok, result.score, result.passed, result.reason) == (True, 0.7, True, "looks fine Dear")


async def test_a_check_that_never_ends_is_stopped() -> None:
    result = await run(
        "def check(case):\n    while True:\n        pass\n",
        SandboxLimits(wall_s=1.0, cpu_s=3, memory_mb=256, output_chars=300),
    )
    assert not result.ok
    assert result.timed_out


@pytest.mark.parametrize(
    ("code", "message"),
    [
        ("def check(case):\n    return open('/etc/passwd').read()\n", "open"),
        ("import socket\ndef check(case):\n    return True\n", "socket"),
        ("import os\ndef check(case):\n    return True\n", "os"),
        ("def check(case):\n    return ().__class__.__bases__\n", ""),
        ("def check(case):\n    return 'not a score'\n", ""),
    ],
)
async def test_files_sockets_imports_and_odd_results_fail_with_a_message(code: str, message: str) -> None:
    result = await run(code)
    assert not result.ok
    assert result.error
    assert message in result.error


async def test_checks_run_side_by_side_and_one_failure_does_not_affect_the_others() -> None:
    good = "def check(case):\n    return True\n"
    bad = "def check(case):\n    raise ValueError('nope')\n"
    results = await asyncio.gather(run(good), run(bad), run(good))
    assert [r.ok for r in results] == [True, False, True]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (True, (1.0, True, "")),
        (False, (0.0, False, "")),
        (0.25, (0.25, False, "")),
        ({"passed": True}, (1.0, True, "")),
    ],
)
def test_results_are_normalised(value: object, expected: tuple[float, bool, str]) -> None:
    assert normalise_result(value) == expected


def test_a_score_outside_zero_to_one_is_refused() -> None:
    with pytest.raises(ValueError, match="0"):
        normalise_result(1.5)
