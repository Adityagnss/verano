"""
Valkey client factory.

Valkey is the BSD-licensed, protocol-compatible fork of Redis (ADR 0001), so the standard
`redis` client library talks to it unchanged. One pooled async client is created per
process and shared by the rate limiter, progress counters and locks.
"""

from redis.asyncio import Redis

from app.core.config import Settings


def create_valkey(settings: Settings) -> Redis:
    return Redis.from_url(settings.valkey_url, decode_responses=False)
