"""
The CLI's only way to reach Verano: the public HTTP API, with the saved token.

Every failure becomes a `CliError` with a message a person can act on: the server is down,
the address is wrong (an HTML page came back), the token is no good, or the API said no.
"""

import os
import socket
from typing import Any

import httpx

from verano import __version__
from verano.config import API_PREFIX, Credentials
from verano.errors import CliError

TIMEOUT_S = 30.0
PAGE_SIZE = 200
MAX_PAGES = 50
TRANSPORT: httpx.BaseTransport | None = None  # tests plug a fake server in here


class ApiClient:
    def __init__(self, url: str, token: str | None = None) -> None:
        self.url = url
        headers = {"User-Agent": f"verano-cli/{__version__}", "Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._http = httpx.Client(
            base_url=url + API_PREFIX, headers=headers, timeout=TIMEOUT_S, transport=TRANSPORT, follow_redirects=False
        )

    @classmethod
    def from_credentials(cls, credentials: Credentials) -> "ApiClient":
        return cls(credentials.url, credentials.token)

    def close(self) -> None:
        self._http.close()

    def get(self, path: str, **params: Any) -> Any:
        return self.request("GET", path, params={k: v for k, v in params.items() if v is not None})

    def pages(self, path: str, **params: Any) -> list[Any]:
        """Every item of a paged list."""
        items: list[Any] = []
        cursor: str | None = None
        for _ in range(MAX_PAGES):
            page = self.get(path, limit=PAGE_SIZE, cursor=cursor, **params)
            items += page["items"]
            cursor = page.get("next_cursor")
            if not cursor:
                return items
        raise CliError(f"{path} has more than {MAX_PAGES * PAGE_SIZE} entries; narrow it down.")

    def post(self, path: str, body: Any = None) -> Any:
        return self.request("POST", path, json=body)

    def put(self, path: str, body: Any = None) -> Any:
        return self.request("PUT", path, json=body)

    def delete(self, path: str) -> Any:
        return self.request("DELETE", path)

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = self._http.request(method, path, **kwargs)
        except httpx.ConnectError as exc:
            raise CliError(
                f"Can't reach Verano at {self.url}.",
                "Is it running? Start it with `docker compose up -d`, or check the address with `verano whoami`.",
            ) from exc
        except httpx.TimeoutException as exc:
            raise CliError(f"Verano at {self.url} didn't answer in {int(TIMEOUT_S)} seconds.") from exc
        except httpx.HTTPError as exc:
            raise CliError(f"The request to {self.url} failed: {exc}.") from exc
        return self._unwrap(response)

    def _unwrap(self, response: httpx.Response) -> Any:
        if response.status_code == 204 or (response.is_success and not response.content):
            return None
        try:
            data = response.json()
        except ValueError:
            raise CliError(
                f"{self.url} answered, but it doesn't look like a Verano server (HTTP {response.status_code}).",
                "Check the address. Use the one you open in the browser, for example http://localhost:8080",
            ) from None
        if response.is_success:
            return data
        raise _api_error(response, data)


def _sign_in_hint() -> str:
    """A token from the environment is a CI secret: logging in on that machine won't replace it."""
    if os.environ.get("VERANO_API_TOKEN"):
        return (
            "The token in VERANO_API_TOKEN no longer works. "
            "Make a new one with `verano token create --name ci` and update the secret."
        )
    return "Run `verano login`."


def _api_error(response: httpx.Response, data: Any) -> CliError:
    error = data.get("error") if isinstance(data, dict) else None
    message = error.get("message") if isinstance(error, dict) else None
    code = response.status_code
    if code == 401:
        return CliError(message or "You are not signed in.", _sign_in_hint(), code)
    if code == 429:
        wait = response.headers.get("retry-after")
        return CliError(message or "Too many requests.", f"Try again in {wait} seconds." if wait else None, code)
    if code >= 500:
        return CliError(f"Verano had a problem (HTTP {code}).", "Check its logs: `docker compose logs backend`.", code)
    details = error.get("details") if isinstance(error, dict) else None
    fields = details.get("fields") if isinstance(details, dict) else None
    if isinstance(fields, list) and fields:
        listed = "; ".join(f"{f.get('field', '?')}: {f.get('message', '')}" for f in fields if isinstance(f, dict))
        return CliError(f"{message or 'The request was refused.'} ({listed})", status=code)
    problems = details.get("problems") if isinstance(details, dict) else None
    if isinstance(problems, list) and problems:
        return CliError(f"{message or 'The request was refused.'}", "\n".join(f"- {p}" for p in problems), code)
    return CliError(message or f"Verano refused the request (HTTP {code}).", status=code)


def token_name() -> str:
    return f"CLI on {socket.gethostname()}"[:100]
