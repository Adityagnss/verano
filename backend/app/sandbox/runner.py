"""
Sandbox runner.

Defines the `Sandbox` protocol and `SubprocessSandbox`, which runs each check in its own child
Python process (the worker) with a minimal environment, a wall-clock timeout that kills the whole
process group, and a capped read of its output. No shared state, so any number can run at once.
Used directly by the sandbox service (server.py) and, when no sandbox URL is set, by the app.
The child is started with `-I` (which ignores PYTHONPATH), so a one-line bootstrap puts the
backend root on its path before importing the worker.
"""

import asyncio
import contextlib
import json
import os
import signal
import sys
from pathlib import Path
from typing import Protocol

from pydantic import ValidationError

from app.sandbox.contract import SandboxLimits, SandboxRequest, SandboxResult

BACKEND_ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP = "import sys; sys.path.insert(0, sys.argv[1]); from app.sandbox.worker import main; main()"
OUTPUT_SLACK_BYTES = 4096
JSON_CHARS_PER_CHAR = 6
DEFAULT_PATH = "/usr/local/bin:/usr/bin:/bin"


class Sandbox(Protocol):
    async def run(self, request: SandboxRequest, limits: SandboxLimits) -> SandboxResult: ...


def _failure(error: str, *, timed_out: bool = False) -> SandboxResult:
    return SandboxResult(ok=False, error=error, reason=error if timed_out else "", timed_out=timed_out)


def _kill_group(process: asyncio.subprocess.Process) -> None:
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(process.pid, signal.SIGKILL)


async def _read_capped(stream: asyncio.StreamReader, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while total < max_bytes:
        chunk = await stream.read(max_bytes - total)
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
    return b"".join(chunks)


class SubprocessSandbox:
    async def run(self, request: SandboxRequest, limits: SandboxLimits) -> SandboxResult:
        env = {"PATH": os.environ.get("PATH", DEFAULT_PATH), "PYTHONPATH": str(BACKEND_ROOT)}
        payload = {"request": request.model_dump(mode="json"), "limits": limits.model_dump(mode="json")}
        stdin = json.dumps(payload).encode()
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-I", "-c", BOOTSTRAP, str(BACKEND_ROOT),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env=env,
            cwd=str(BACKEND_ROOT),
            start_new_session=True,
        )  # fmt: skip
        max_bytes = limits.output_chars * JSON_CHARS_PER_CHAR + OUTPUT_SLACK_BYTES
        try:
            raw = await asyncio.wait_for(self._exchange(process, stdin, max_bytes), timeout=limits.wall_s)
        except TimeoutError:
            return _failure(
                f"The check did not finish within {limits.wall_s:g} seconds and was stopped.", timed_out=True
            )
        finally:
            _kill_group(process)
            with contextlib.suppress(Exception):
                await process.wait()
        return self._parse(raw)

    @staticmethod
    async def _exchange(process: asyncio.subprocess.Process, stdin: bytes, max_bytes: int) -> bytes:
        if process.stdin is None or process.stdout is None:
            raise RuntimeError("The check process has no pipes.")
        with contextlib.suppress(BrokenPipeError, ConnectionResetError):
            process.stdin.write(stdin)
            await process.stdin.drain()
            process.stdin.close()
        data = await _read_capped(process.stdout, max_bytes)
        await process.wait()
        return data

    @staticmethod
    def _parse(raw: bytes) -> SandboxResult:
        lines = raw.decode("utf-8", errors="replace").strip().splitlines()
        if not lines:
            return _failure("The check stopped without a result (it may have run out of memory or CPU time).")
        try:
            return SandboxResult.model_validate_json(lines[-1])
        except ValidationError:
            return _failure("The check produced output that could not be read.")
