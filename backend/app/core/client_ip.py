"""
Client IP resolution behind reverse proxies.

The address a request came from decides auth throttling, so it must not be spoofable.
`X-Forwarded-For` is honoured only when the direct peer is one of `VERANO_TRUSTED_PROXIES`
(addresses or CIDR ranges, empty by default). The header is then read right to left,
skipping hops that are themselves trusted proxies, and the first untrusted address is the
client: anything further left was written by the client and cannot be trusted. With no
trusted proxies configured, the header is ignored and the direct peer is used.
"""

import ipaddress
from typing import Annotated

from fastapi import Depends, Request

from app.core.container import SettingsDep

Network = ipaddress.IPv4Network | ipaddress.IPv6Network
UNKNOWN = "unknown"


def parse_networks(entries: list[str]) -> list[Network]:
    return [ipaddress.ip_network(entry.strip(), strict=False) for entry in entries if entry.strip()]


def _trusted(address: str, networks: list[Network]) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return any(ip in network for network in networks)


def resolve_client_ip(peer: str | None, forwarded_for: str | None, trusted: list[Network]) -> str:
    if not peer:
        return UNKNOWN
    if not forwarded_for or not _trusted(peer, trusted):
        return peer
    hops = [hop.strip() for hop in forwarded_for.split(",") if hop.strip()]
    untrusted = [hop for hop in reversed(hops) if not _trusted(hop, trusted)]
    return untrusted[0] if untrusted else peer


def client_ip(request: Request, settings: SettingsDep) -> str:
    peer = request.client.host if request.client else None
    return resolve_client_ip(peer, request.headers.get("x-forwarded-for"), parse_networks(settings.trusted_proxies))


ClientIP = Annotated[str, Depends(client_ip)]
