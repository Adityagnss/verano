"""Unit tests for client IP resolution behind trusted and untrusted peers."""

import pytest

from app.core.client_ip import parse_networks, resolve_client_ip

pytestmark = pytest.mark.unit

PROXIES = parse_networks(["10.0.0.0/8", "fd00::/8"])


@pytest.mark.parametrize(
    ("peer", "forwarded_for", "expected"),
    [
        ("203.0.113.9", "198.51.100.1", "203.0.113.9"),
        ("10.0.0.2", "198.51.100.1", "198.51.100.1"),
        ("10.0.0.2", "6.6.6.6, 198.51.100.1", "198.51.100.1"),
        ("10.0.0.2", "198.51.100.1, 10.0.0.7", "198.51.100.1"),
        ("10.0.0.2", "10.0.0.7", "10.0.0.2"),
        ("10.0.0.2", None, "10.0.0.2"),
        ("fd00::5", "2001:db8::1", "2001:db8::1"),
        (None, "198.51.100.1", "unknown"),
    ],
)
def test_forwarded_for_is_trusted_only_from_configured_proxies_and_read_right_to_left(
    peer: str | None, forwarded_for: str | None, expected: str
) -> None:
    assert resolve_client_ip(peer, forwarded_for, PROXIES) == expected


def test_with_no_trusted_proxies_the_header_is_always_ignored() -> None:
    assert resolve_client_ip("10.0.0.2", "198.51.100.1", []) == "10.0.0.2"
