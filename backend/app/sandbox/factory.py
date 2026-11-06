"""
Sandbox factory.

Chooses the sandbox implementation from configuration: the HTTP client when a sandbox service URL is
set (production, tests of the container), otherwise an in-machine subprocess (local development).
"""

from app.sandbox.client import HttpSandbox
from app.sandbox.runner import Sandbox, SubprocessSandbox


def build_sandbox(url: str | None) -> Sandbox:
    return HttpSandbox(url) if url else SubprocessSandbox()
