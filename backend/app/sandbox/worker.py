"""
Sandbox worker.

Run in a child process by SubprocessSandbox: reads one JSON {request, limits} from stdin, applies OS
resource limits, moves into a fresh temp dir, disables network and process spawning, then runs the
user's code with a restricted `__builtins__` and an allow-listed `__import__`, and prints one JSON
SandboxResult line. Defence in depth only: the sandbox container itself has no network and no secrets.
Allowed modules are handed over as proxies that hide private names and unlisted submodules, so
`typing.sys` and similar routes back to `os` do not exist. User code is also rejected at parse time
if it touches any name or attribute starting with an underscore.
"""

import ast
import builtins
import json
import os
import resource
import socket
import subprocess
import sys
import tempfile
import types
from collections.abc import Callable
from typing import Any

from app.sandbox.contract import SandboxLimits, SandboxRequest, SandboxResult, normalise_result

ALLOWED_MODULES = frozenset(
    {
        "re", "json", "math", "statistics", "string", "itertools", "functools", "collections", "datetime",
        "decimal", "fractions", "difflib", "unicodedata", "textwrap", "typing", "dataclasses", "html",
        "urllib.parse", "base64", "hashlib",
    }
)  # fmt: skip
PARENT_PACKAGES = frozenset(name.split(".")[0] for name in ALLOWED_MODULES if "." in name)
_SAFE_BUILTIN_TEXT = (
    "abs all any ascii bin bool bytearray bytes "
    "callable chr complex dict divmod enumerate filter float "
    "format frozenset hash hex int isinstance issubclass iter "
    "len list map max min next object oct "
    "ord pow range repr reversed round set slice "
    "sorted str sum tuple zip property staticmethod classmethod "
    "super True False None NotImplemented Ellipsis Exception BaseException "
    "ValueError TypeError KeyError IndexError AttributeError ZeroDivisionError ArithmeticError LookupError "
    "RuntimeError StopIteration OverflowError AssertionError NameError "
)
SAFE_BUILTIN_NAMES = frozenset(_SAFE_BUILTIN_TEXT.split())
FILE_DESCRIPTOR_LIMIT = 32
PROCESS_LIMIT = 0
ERROR_MESSAGE_CHARS = 200
CODE_FILENAME = "<check>"
PRIVATE_PREFIX = "_"
_real_import = builtins.__import__


def _apply_limits(limits: SandboxLimits) -> None:
    wanted = {
        "RLIMIT_CPU": limits.cpu_s,
        "RLIMIT_AS": limits.memory_mb * 1024 * 1024,
        "RLIMIT_NOFILE": FILE_DESCRIPTOR_LIMIT,
        "RLIMIT_NPROC": PROCESS_LIMIT,
    }
    for name, value in wanted.items():
        kind = getattr(resource, name, None)
        if kind is None:
            continue
        try:
            resource.setrlimit(kind, (value, value))
        except (ValueError, OSError):
            continue


def _denied(*_: object, **__: object) -> Any:
    raise PermissionError("This operation is not allowed in a check.")


def _block_network_and_processes() -> None:
    for name in ("socket", "create_connection", "getaddrinfo", "gethostbyname", "socketpair"):
        setattr(socket, name, _denied)
    for name in ("Popen", "run", "call", "check_call", "check_output", "getoutput", "getstatusoutput"):
        setattr(subprocess, name, _denied)
    names = ("system", "fork", "forkpty", "posix_spawn", "posix_spawnp", "popen", "kill", "killpg")
    exec_and_spawn = [n for n in dir(os) if n.startswith(("exec", "spawn"))]
    for name in (*names, *exec_and_spawn):
        if hasattr(os, name):
            setattr(os, name, _denied)


def _public_proxy(module: types.ModuleType) -> types.ModuleType:
    proxy = types.ModuleType(module.__name__)
    for name, value in vars(module).items():
        if name.startswith(PRIVATE_PREFIX):
            continue
        if isinstance(value, types.ModuleType):
            if value.__name__ in ALLOWED_MODULES:
                setattr(proxy, name, _public_proxy(value))
            continue
        setattr(proxy, name, value)
    return proxy


def _guarded_import(
    name: str,
    globals: Any = None,
    locals: Any = None,
    fromlist: Any = (),
    level: int = 0,
) -> types.ModuleType:
    if level != 0 or (name not in ALLOWED_MODULES and name not in PARENT_PACKAGES):
        raise ImportError(f"Importing '{name}' is not allowed in a check.")
    real = _real_import(name, None, None, fromlist or (), 0)
    if fromlist:
        return _public_proxy(sys.modules[name])
    return _public_proxy(real)


def _guarded_getattr(obj: object, name: str, *default: object) -> object:
    if not isinstance(name, str) or name.startswith(PRIVATE_PREFIX):
        raise AttributeError("Access to private attributes is not allowed in a check.")
    return getattr(obj, name, *default)


def _safe_builtins() -> dict[str, object]:
    safe: dict[str, object] = {name: getattr(builtins, name) for name in SAFE_BUILTIN_NAMES}
    safe["__import__"] = _guarded_import
    safe["__build_class__"] = builtins.__build_class__
    safe["getattr"] = _guarded_getattr
    safe["hasattr"] = lambda obj, name: hasattr(obj, name) if not str(name).startswith(PRIVATE_PREFIX) else False
    return safe


def _reject_private_access(tree: ast.AST) -> None:
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr.startswith(PRIVATE_PREFIX):
            raise PermissionError("Private attribute access is not allowed in a check.")
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            raise PermissionError("Names starting with double underscores are not allowed in a check.")


def _load_check(code: str) -> Callable[[dict[str, Any]], object]:
    tree = ast.parse(code, CODE_FILENAME)
    _reject_private_access(tree)
    namespace: dict[str, Any] = {"__builtins__": _safe_builtins(), "__name__": "check_module"}
    exec(compile(tree, CODE_FILENAME, "exec"), namespace)
    check = namespace.get("check")
    if not callable(check):
        raise ValueError("The code must define a function named check(case).")
    return check  # type: ignore[no-any-return]


def _describe(exc: BaseException) -> str:
    message = " ".join(str(exc).split())[:ERROR_MESSAGE_CHARS]
    return f"{type(exc).__name__}: {message}" if message else type(exc).__name__


def execute(request: SandboxRequest, limits: SandboxLimits) -> SandboxResult:
    try:
        check = _load_check(request.code)
        score, passed, reason = normalise_result(check(request.case))
    except BaseException as exc:
        return SandboxResult(ok=False, error=_describe(exc))
    return SandboxResult(ok=True, score=score, passed=passed, reason=reason[: limits.output_chars])


def main() -> None:
    out = sys.stdout
    try:
        payload = json.loads(sys.stdin.read())
        request = SandboxRequest.model_validate(payload["request"])
        limits = SandboxLimits.model_validate(payload["limits"])
    except Exception as exc:
        out.write(SandboxResult(ok=False, error=_describe(exc)).model_dump_json() + "\n")
        return
    _apply_limits(limits)
    os.chdir(tempfile.mkdtemp(prefix="check-"))
    _block_network_and_processes()
    out.write(execute(request, limits).model_dump_json() + "\n")
    out.flush()


if __name__ == "__main__":
    main()
