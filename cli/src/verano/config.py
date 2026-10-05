"""
Where the CLI keeps its sign-in and which server it talks to.

`VERANO_URL` and `VERANO_API_TOKEN` win over the saved file, so CI needs no login step. The
file holds a personal API token and is written readable by its owner only.
"""

import json
import os
import stat
import sys
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path

from verano.errors import CliError

DEFAULT_URL = "http://localhost:8080"
API_PREFIX = "/api/v1"
ENV_URL = "VERANO_URL"
ENV_TOKEN = "VERANO_API_TOKEN"


@dataclass(frozen=True)
class Credentials:
    url: str
    token: str
    email: str | None = None
    token_id: str | None = None
    source: str = "file"


def normalize_url(raw: str) -> str:
    """`http://host:port`, without a trailing slash or the API path, which the CLI adds itself."""
    url = raw.strip().rstrip("/")
    if url.endswith(API_PREFIX):
        url = url.removesuffix(API_PREFIX).rstrip("/")
    if not url.startswith(("http://", "https://")) or "://" in url[8:]:
        raise CliError(
            f"'{raw}' is not a server address.",
            "Write it with http:// or https://, for example http://localhost:8080",
        )
    host = url.split("://", 1)[1]
    if not host or host.startswith(("/", ":")):
        raise CliError(f"'{raw}' is not a server address.", "Write it like http://localhost:8080")
    return url


def config_dir(env: Mapping[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    if env.get("XDG_CONFIG_HOME"):
        return Path(env["XDG_CONFIG_HOME"]) / "verano"
    if sys.platform == "win32" and env.get("APPDATA"):
        return Path(env["APPDATA"]) / "verano"
    return Path.home() / ".config" / "verano"


def credentials_path(env: Mapping[str, str] | None = None) -> Path:
    return config_dir(env) / "credentials.json"


def load_credentials(env: Mapping[str, str] | None = None) -> Credentials | None:
    env = os.environ if env is None else env
    if env.get(ENV_TOKEN):
        return Credentials(
            url=normalize_url(env.get(ENV_URL) or DEFAULT_URL), token=env[ENV_TOKEN].strip(), source="environment"
        )
    path = credentials_path(env)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        return Credentials(
            url=normalize_url(env.get(ENV_URL) or data["url"]),
            token=data["token"],
            email=data.get("email"),
            token_id=data.get("token_id"),
        )
    except (ValueError, KeyError, TypeError) as exc:
        raise CliError(f"The saved sign-in at {path} can't be read.", "Run `verano login` again.") from exc


def save_credentials(credentials: Credentials, env: Mapping[str, str] | None = None) -> Path:
    path = credentials_path(env)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {k: v for k, v in asdict(credentials).items() if k != "source" and v is not None}
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    descriptor = os.open(path, flags, stat.S_IRUSR | stat.S_IWUSR)
    with os.fdopen(descriptor, "w") as handle:
        handle.write(json.dumps(data, indent=2) + "\n")
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    return path


def delete_credentials(env: Mapping[str, str] | None = None) -> bool:
    path = credentials_path(env)
    if path.exists():
        path.unlink()
        return True
    return False
