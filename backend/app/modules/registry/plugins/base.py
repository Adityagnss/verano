"""
Provider client contract and shared HTTP handling.

Every provider plugin implements `ProviderClient` (list models, validate a key) and
registers its class in `PROVIDER_CLIENTS` under the `client` name used in
`providers.yaml`. `ProviderHttp` performs the listing requests over the process-wide
pooled HTTP client and turns every failure into a typed error with a message that tells
the user what to do. The status → error mapping is a table, not a branch chain.
"""

from typing import Any, ClassVar, Protocol

import httpx

from app.core.errors import (
    ModelNotFound,
    ProviderAuthError,
    ProviderBadRequest,
    ProviderError,
    ProviderTimeout,
    ProviderUnavailable,
    RateLimited,
    parse_retry_after,
    provider_error,
)
from app.core.registry import Registry
from app.modules.registry.schemas import ProviderSpec, RawModel

STATUS_ERRORS: dict[int, type[ProviderError]] = {
    401: ProviderAuthError,
    403: ProviderAuthError,
    404: ModelNotFound,
    408: ProviderTimeout,
    429: RateLimited,
}

UNREACHABLE = "Can't reach {provider} at {url}. Check that it's running and the address is right."


class ProviderClient(Protocol):
    client_name: ClassVar[str]

    async def list_models(self, api_key: str | None, base_url: str) -> list[RawModel]: ...

    async def validate(self, api_key: str | None, base_url: str) -> None: ...


PROVIDER_CLIENTS: Registry[type["BaseProviderClient"]] = Registry("provider client")


def error_class_for(status: int, body: str, auth_markers: list[str]) -> type[ProviderError]:
    if any(marker in body for marker in auth_markers):
        return ProviderAuthError
    fallback = ProviderUnavailable if status >= 500 else ProviderBadRequest
    return STATUS_ERRORS.get(status, fallback)


def provider_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text[:300]
    message = payload.get("error", payload) if isinstance(payload, dict) else payload
    if isinstance(message, dict):
        message = message.get("message", message)
    return str(message)[:300]


class ProviderHttp:
    def __init__(self, http: httpx.AsyncClient, spec: ProviderSpec) -> None:
        self._http = http
        self._spec = spec

    async def get_json(self, url: str, headers: dict[str, str], params: dict[str, Any] | None = None) -> Any:
        try:
            response = await self._http.get(url, headers=headers, params=params)
        except httpx.TimeoutException as exc:
            raise provider_error(ProviderTimeout, self._spec.display_name, str(exc)) from exc
        except httpx.TransportError as exc:
            message = UNREACHABLE.format(provider=self._spec.display_name, url=url)
            raise ProviderUnavailable(message) from exc
        if response.is_success:
            return response.json()
        raise self._error(response)

    async def post_json(self, url: str, headers: dict[str, str], body: dict[str, Any]) -> Any:
        try:
            response = await self._http.post(url, headers=headers, json=body)
        except httpx.TransportError as exc:
            raise ProviderUnavailable(UNREACHABLE.format(provider=self._spec.display_name, url=url)) from exc
        if response.is_success:
            return response.json()
        raise self._error(response)

    def _error(self, response: httpx.Response) -> ProviderError:
        error_cls = error_class_for(response.status_code, response.text, self._spec.auth_error_markers)
        error = provider_error(
            error_cls,
            self._spec.display_name,
            provider_detail(response),
            retry_after_s=parse_retry_after(response.headers.get("retry-after")),
        )
        error.details["status"] = response.status_code
        return error


class BaseProviderClient:
    client_name: ClassVar[str]

    def __init__(self, spec: ProviderSpec, http: httpx.AsyncClient, **context: Any) -> None:
        self.spec = spec
        self.http = ProviderHttp(http, spec)
        self.context = context

    async def list_models(self, api_key: str | None, base_url: str) -> list[RawModel]:
        raise NotImplementedError

    async def validate(self, api_key: str | None, base_url: str) -> None:
        if self.spec.key_check_path:
            headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
            await self.http.get_json(f"{base_url.rstrip('/')}{self.spec.key_check_path}", headers)
        else:
            await self.list_models(api_key, base_url)
