"""
The client: `Verano(...).prompt("name", label="production")`.

Each call asks the server for the prompt the label points at, sending the ETag of the saved copy so an
unchanged prompt costs an empty 304 answer. The last good copy is kept on disk. If Verano cannot be reached
(no connection, a timeout, a server error) the saved copy is returned with `from_cache=True` and a warning, so an
outage never takes your app down; with no saved copy the error says so. A "no" from Verano (a revoked token, an
unknown label) is raised, never hidden behind the cache. Only the standard library is used.
"""

import hashlib
import json
import os
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from verano_sdk import __version__
from verano_sdk.errors import VeranoError, VeranoRefused, VeranoUnreachable

API_PREFIX = "/api/v1"
PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
ENV_URL, ENV_TOKEN, ENV_PROJECT = "VERANO_URL", "VERANO_API_TOKEN", "VERANO_PROJECT_ID"


@dataclass(frozen=True)
class Prompt:
    name: str
    label: str | None
    version: int
    version_id: str
    system_template: str | None
    user_template: str | None
    variables: list[str]
    default_params: dict[str, Any]
    updated_at: str
    from_cache: bool = False
    etag: str | None = field(default=None, repr=False)

    def render(self, **values: Any) -> tuple[str | None, str | None]:
        """The (system, user) text with `{{ name }}` placeholders filled in. Every placeholder needs a value."""
        missing = [v for v in self.variables if v not in values]
        if missing:
            raise VeranoError(f"Missing values for: {', '.join(missing)}.")

        def fill(text: str | None) -> str | None:
            return None if text is None else PLACEHOLDER.sub(lambda m: str(values[m.group(1)]), text)

        return fill(self.system_template), fill(self.user_template)


def _cache_root(explicit: str | os.PathLike[str] | None) -> Path:
    if explicit is not None:
        return Path(explicit)
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "verano-sdk"


def _as_prompt(data: dict[str, Any], etag: str | None, from_cache: bool) -> Prompt:
    return Prompt(
        name=data["name"],
        label=data.get("label"),
        version=int(data["version"]),
        version_id=str(data["version_id"]),
        system_template=data.get("system_template"),
        user_template=data.get("user_template"),
        variables=list(data.get("variables", [])),
        default_params=dict(data.get("default_params", {})),
        updated_at=str(data.get("updated_at", "")),
        from_cache=from_cache,
        etag=etag,
    )


class Verano:
    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        project_id: str | None = None,
        cache_dir: str | os.PathLike[str] | None = None,
        timeout: float = 3.0,
        max_age: float = 0.0,
    ) -> None:
        url = base_url or os.environ.get(ENV_URL)
        key = token or os.environ.get(ENV_TOKEN)
        project = project_id or os.environ.get(ENV_PROJECT)
        if not url or not key or not project:
            raise VeranoError(
                "Give the server address, a token and the project id, or set "
                f"{ENV_URL}, {ENV_TOKEN} and {ENV_PROJECT}. "
                "Make a read-only token with `verano token create --read-only`."
            )
        self._base = url.rstrip("/").removesuffix(API_PREFIX)
        self._token, self._project = key, project
        self._cache = _cache_root(cache_dir)
        self._timeout, self._max_age = timeout, max_age
        self._memory: dict[str, tuple[float, Prompt]] = {}

    def prompt(self, name: str, label: str | None = "production", version: int | None = None) -> Prompt:
        """The prompt `label` points at (or a given version, or with `label=None` the latest saved one)."""
        if version is not None:
            label = None
        key = self._key(name, label, version)
        hit = self._memory.get(key)
        if hit is not None and self._max_age > 0 and time.monotonic() - hit[0] < self._max_age:
            return hit[1]
        saved = self._read(key)
        try:
            fresh = self._fetch(name, label, version, saved.etag if saved else None, saved)
        except VeranoUnreachable as outage:
            if saved is None:
                raise
            warnings.warn(
                f"Verano could not be reached ({outage}); using the saved copy of '{name}' (version {saved.version}).",
                stacklevel=2,
            )
            return Prompt(**{**saved.__dict__, "from_cache": True})
        self._memory[key] = (time.monotonic(), fresh)
        return fresh

    def _key(self, name: str, label: str | None, version: int | None) -> str:
        raw = f"{self._base}|{self._project}|{name}|{label}|{version}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    def _fetch(
        self, name: str, label: str | None, version: int | None, etag: str | None, saved: Prompt | None
    ) -> Prompt:
        query = urllib.parse.urlencode({k: v for k, v in (("label", label), ("version", version)) if v is not None})
        path = f"{API_PREFIX}/projects/{self._project}/prompt-by-name/{urllib.parse.quote(name, safe='')}"
        request = urllib.request.Request(
            f"{self._base}{path}" + (f"?{query}" if query else ""),
            headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/json",
                "User-Agent": f"verano-sdk-python/{__version__}",
                **({"If-None-Match": etag} if etag and saved else {}),
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                body = json.loads(response.read())
                fresh = _as_prompt(body, response.headers.get("ETag"), False)
        except urllib.error.HTTPError as error:
            if error.code == 304 and saved is not None:
                return Prompt(**{**saved.__dict__, "from_cache": False})
            if error.code >= 500:
                raise VeranoUnreachable(f"the server answered {error.code}") from error
            raise VeranoRefused(_message(error), error.code) from error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise VeranoUnreachable(str(getattr(error, "reason", error))) from error
        except (ValueError, KeyError) as error:
            raise VeranoUnreachable("the answer was not a Verano prompt") from error
        self._write(self._key(name, label, version), fresh)
        return fresh

    def _read(self, key: str) -> Prompt | None:
        try:
            data = json.loads((self._cache / f"{key}.json").read_text(encoding="utf-8"))
            return _as_prompt(data["prompt"], data.get("etag"), True)
        except (OSError, ValueError, KeyError):
            return None

    def _write(self, key: str, prompt: Prompt) -> None:
        """Atomic, best effort: a cache that cannot be written must never break the app."""
        try:
            self._cache.mkdir(parents=True, exist_ok=True)
            payload = {"etag": prompt.etag, "prompt": {k: v for k, v in prompt.__dict__.items() if k != "etag"}}
            handle, temp = tempfile.mkstemp(dir=self._cache, suffix=".tmp")
            with os.fdopen(handle, "w", encoding="utf-8") as out:
                json.dump(payload, out)
            os.replace(temp, self._cache / f"{key}.json")
        except OSError:
            return


def _message(error: urllib.error.HTTPError) -> str:
    try:
        return str(json.loads(error.read())["error"]["message"])
    except (ValueError, KeyError, TypeError):
        return f"Verano refused the request (HTTP {error.code})."
