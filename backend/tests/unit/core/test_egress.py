"""Calling a user's address safely (ADR 0025): internal addresses are refused, every redirect is checked, replies
are capped.
"""

import httpx
import pytest

from app.core.egress import EgressBlocked, EgressPolicy, guarded_request, is_public_address

POLICY = EgressPolicy(allowed_hosts=frozenset(), max_bytes=1000, timeout_s=5.0, max_redirects=3)


@pytest.mark.parametrize(
    ("address", "public"),
    [
        ("8.8.8.8", True),
        ("2606:4700:4700::1111", True),
        ("127.0.0.1", False),
        ("10.0.0.5", False),
        ("172.16.0.1", False),
        ("192.168.1.1", False),
        ("169.254.169.254", False),
        ("100.64.0.1", False),
        ("0.0.0.0", False),
        ("::1", False),
        ("fd00::1", False),
        ("::ffff:10.0.0.1", False),
        ("not an address", False),
    ],
)
def test_only_public_addresses_are_public(address: str, public: bool) -> None:
    assert is_public_address(address) is public


async def test_a_public_address_is_called_and_the_reply_is_returned() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["host"] == "8.8.8.8"
        return httpx.Response(200, json={"answer": "ok"})

    reply = await guarded_request(
        "POST", "http://8.8.8.8/ask", headers={}, body=b"{}", policy=POLICY, transport=httpx.MockTransport(handler)
    )
    assert reply.status == 200
    assert b"ok" in reply.body
    assert not reply.truncated


@pytest.mark.parametrize("url", ["http://127.0.0.1/x", "http://169.254.169.254/latest", "http://10.1.2.3/"])
async def test_internal_addresses_are_refused_unless_the_host_is_allowed(url: str) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200))
    with pytest.raises(EgressBlocked):
        await guarded_request("GET", url, headers={}, body=None, policy=POLICY, transport=transport)
    host = url.split("//")[1].split("/")[0]
    allowed = EgressPolicy(frozenset({host}), 1000, 5.0, 3)
    reply = await guarded_request("GET", url, headers={}, body=None, policy=allowed, transport=transport)
    assert reply.status == 200


async def test_a_redirect_to_an_internal_address_is_refused() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "http://127.0.0.1/admin"})

    with pytest.raises(EgressBlocked):
        await guarded_request(
            "GET", "http://8.8.8.8/x", headers={}, body=None, policy=POLICY, transport=httpx.MockTransport(handler)
        )


async def test_too_many_redirects_and_unsafe_urls_are_refused() -> None:
    loop = httpx.MockTransport(lambda request: httpx.Response(302, headers={"Location": "http://8.8.8.8/again"}))
    with pytest.raises(EgressBlocked):
        await guarded_request("GET", "http://8.8.8.8/x", headers={}, body=None, policy=POLICY, transport=loop)
    for url in ("file:///etc/passwd", "ftp://8.8.8.8/x", "http://user:pass@8.8.8.8/x"):
        with pytest.raises(EgressBlocked):
            await guarded_request("GET", url, headers={}, body=None, policy=POLICY, transport=loop)


async def test_a_long_reply_is_cut_and_flagged() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b"x" * 5000))
    reply = await guarded_request("GET", "http://8.8.8.8/x", headers={}, body=None, policy=POLICY, transport=transport)
    assert reply.truncated
    assert len(reply.body) <= 1000
