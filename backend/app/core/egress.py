"""
Guarded outbound HTTP for user-supplied URLs (SSRF protection).

Verano calls URLs that users type in, so every request goes through `guarded_request`.
It validates the URL (http or https, no credentials), resolves the host once, refuses the
call unless every resolved address is public (or the host is on the owner's allow-list),
then connects to that exact IP while sending the original Host header and TLS SNI, so a
second DNS lookup can never swap in a private address. Redirects are never followed
automatically: each hop is followed by hand and re-validated with the same rules.
Responses are streamed and cut at `max_bytes`; `timeout_s` bounds the whole call.
Callers build `EgressPolicy` from settings. Tests inject an `httpx.MockTransport`; the
address validation still runs, only the network send is replaced.
"""

import asyncio
import ipaddress
import socket
import time
from dataclasses import dataclass
from typing import Final
from urllib.parse import urljoin, urlsplit

import httpx

from app.core.errors import AppError, ProviderTimeout, ProviderUnavailable

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address

BLOCKED_NETWORKS: Final[tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]] = tuple(
    ipaddress.ip_network(cidr)
    for cidr in (
        "0.0.0.0/8",
        "10.0.0.0/8",
        "100.64.0.0/10",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "172.16.0.0/12",
        "192.0.0.0/24",
        "192.0.2.0/24",
        "192.88.99.0/24",
        "192.168.0.0/16",
        "198.18.0.0/15",
        "198.51.100.0/24",
        "203.0.113.0/24",
        "224.0.0.0/4",
        "240.0.0.0/4",
        "::/128",
        "::1/128",
        "64:ff9b::/96",
        "100::/64",
        "2001:db8::/32",
        "fc00::/7",
        "fe80::/10",
        "ff00::/8",
        "169.254.169.254/32",
        "100.100.100.200/32",
        "fd00:ec2::254/128",
    )
)

REDIRECT_STATUSES: Final[frozenset[int]] = frozenset({301, 302, 303, 307, 308})
METHOD_RESETTING_REDIRECTS: Final[frozenset[int]] = frozenset({301, 302, 303})
CROSS_HOST_STRIPPED_HEADERS: Final[frozenset[str]] = frozenset({"authorization", "cookie", "proxy-authorization"})
DEFAULT_PORTS: Final[dict[str, int]] = {"http": 80, "https": 443}
ALLOW_HINT: Final[str] = "The workspace owner can allow this host in the egress allow-list setting."


class EgressBlocked(AppError):
    status_code = 400
    code = "egress_blocked"


@dataclass(frozen=True)
class EgressPolicy:
    allowed_hosts: frozenset[str]
    max_bytes: int
    timeout_s: float
    max_redirects: int


@dataclass
class GuardedResponse:
    status: int
    headers: dict[str, str]
    body: bytes
    truncated: bool
    elapsed_ms: float


@dataclass(frozen=True)
class _Target:
    scheme: str
    host: str
    port: int
    path_and_query: str


def _blocked(what: str, host: str | None = None) -> EgressBlocked:
    details = {"host": host} if host else {}
    return EgressBlocked(f"{what} {ALLOW_HINT}", details)


def is_public_address(ip: str) -> bool:
    try:
        address: IPAddress = ipaddress.ip_address(ip.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    if any(address in network for network in BLOCKED_NETWORKS if network.version == address.version):
        return False
    return address.is_global and not address.is_multicast


def _parse_target(url: str) -> _Target:
    parts = urlsplit(url)
    if parts.scheme not in DEFAULT_PORTS:
        raise EgressBlocked("Only http and https addresses can be called.", {"url": url})
    if parts.username is not None or parts.password is not None:
        raise EgressBlocked("Addresses with a username or password in them are not allowed.", {"url": url})
    try:
        host = parts.hostname
        port = parts.port or DEFAULT_PORTS[parts.scheme]
    except ValueError as error:
        raise EgressBlocked("This address is not a valid URL.", {"url": url}) from error
    if not host:
        raise EgressBlocked("This address has no host name.", {"url": url})
    path = parts.path or "/"
    return _Target(parts.scheme, host.lower(), port, f"{path}?{parts.query}" if parts.query else path)


async def resolve_public(host: str, port: int, policy: EgressPolicy) -> str:
    host = host.lower()
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as error:
        raise EgressBlocked(f"The host {host} could not be found.", {"host": host}) from error
    addresses = [str(info[4][0]) for info in infos]
    if not addresses:
        raise EgressBlocked(f"The host {host} could not be found.", {"host": host})
    if host in policy.allowed_hosts:
        return addresses[0]
    if not all(is_public_address(address) for address in addresses):
        raise _blocked(f"Calls to {host} were blocked because it points to a private or internal address.", host)
    return addresses[0]


def _host_header(target: _Target) -> str:
    bracketed = f"[{target.host}]" if ":" in target.host else target.host
    return bracketed if target.port == DEFAULT_PORTS[target.scheme] else f"{bracketed}:{target.port}"


def _ip_url(target: _Target, ip: str) -> str:
    bracketed = f"[{ip}]" if ":" in ip else ip
    return f"{target.scheme}://{bracketed}:{target.port}{target.path_and_query}"


def _build_request(method: str, target: _Target, ip: str, headers: dict[str, str], body: bytes | None) -> httpx.Request:
    sent = {name: value for name, value in headers.items() if name.lower() != "host"}
    sent["Host"] = _host_header(target)
    extensions = {"sni_hostname": target.host} if target.scheme == "https" else {}
    return httpx.Request(method, _ip_url(target, ip), headers=sent, content=body, extensions=extensions)


async def _read_limited(response: httpx.Response, max_bytes: int) -> tuple[bytes, bool]:
    chunks: list[bytes] = []
    size = 0
    async for chunk in response.aiter_bytes():
        remaining = max_bytes - size
        if len(chunk) > remaining:
            chunks.append(chunk[:remaining])
            return b"".join(chunks), True
        chunks.append(chunk)
        size += len(chunk)
    return b"".join(chunks), False


async def _send_once(
    request: httpx.Request, policy: EgressPolicy, transport: httpx.AsyncBaseTransport | None
) -> tuple[int, dict[str, str], bytes, bool]:
    async with httpx.AsyncClient(transport=transport, follow_redirects=False, trust_env=False, timeout=None) as client:
        response = await client.send(request, stream=True)
        try:
            body, truncated = await _read_limited(response, policy.max_bytes)
        finally:
            await response.aclose()
        return response.status_code, dict(response.headers), body, truncated


def _next_hop(
    current_url: str, status: int, location: str, method: str, headers: dict[str, str], body: bytes | None
) -> tuple[str, str, dict[str, str], bytes | None]:
    next_url = urljoin(current_url, location)
    if status in METHOD_RESETTING_REDIRECTS and method != "HEAD":
        method, body = "GET", None
        headers = {
            name: value for name, value in headers.items() if name.lower() not in {"content-type", "content-length"}
        }
    if urlsplit(next_url).hostname != urlsplit(current_url).hostname:
        headers = {name: value for name, value in headers.items() if name.lower() not in CROSS_HOST_STRIPPED_HEADERS}
    return next_url, method, headers, body


async def _follow(
    method: str,
    url: str,
    headers: dict[str, str],
    body: bytes | None,
    policy: EgressPolicy,
    transport: httpx.AsyncBaseTransport | None,
) -> GuardedResponse:
    started = time.perf_counter()
    for _ in range(policy.max_redirects + 1):
        target = _parse_target(url)
        ip = await resolve_public(target.host, target.port, policy)
        request = _build_request(method, target, ip, headers, body)
        status, response_headers, content, truncated = await _send_once(request, policy, transport)
        location = response_headers.get("location")
        if status not in REDIRECT_STATUSES or not location:
            elapsed_ms = (time.perf_counter() - started) * 1000
            return GuardedResponse(status, response_headers, content, truncated, elapsed_ms)
        url, method, headers, body = _next_hop(url, status, location, method, headers, body)
    raise EgressBlocked(
        f"The app redirected more than {policy.max_redirects} times.", {"max_redirects": policy.max_redirects}
    )


async def guarded_request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None,
    body: bytes | None,
    policy: EgressPolicy,
    transport: httpx.AsyncBaseTransport | None = None,
) -> GuardedResponse:
    try:
        async with asyncio.timeout(policy.timeout_s):
            return await _follow(method.upper(), url, dict(headers or {}), body, policy, transport)
    except TimeoutError as error:
        raise ProviderTimeout(f"The app did not answer within {policy.timeout_s:g} seconds.") from error
    except httpx.HTTPError as error:
        raise ProviderUnavailable(f"The app could not be reached: {error.__class__.__name__}.") from error
