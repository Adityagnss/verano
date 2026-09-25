"""
Fixed-window request throttling on Valkey.

A small, general limiter for protecting our own endpoints (as opposed to the gateway's
adaptive limiter, which protects provider budgets). Each `hit` increments a counter that
expires at the end of its window; when the count passes the limit it returns how many
seconds remain, which callers turn into a 429 with `Retry-After`. Counting and expiry
happen in one pipeline, so concurrent requests from many processes are counted exactly.
"""

from redis.asyncio import Redis


class FixedWindowLimiter:
    def __init__(self, valkey: Redis, prefix: str = "throttle") -> None:
        self._valkey = valkey
        self._prefix = prefix

    async def hit(self, key: str, limit: int, window_s: int) -> float | None:
        name = f"{self._prefix}:{key}"
        pipe = self._valkey.pipeline(transaction=True)
        pipe.incr(name)
        pipe.expire(name, window_s, nx=True)
        pipe.ttl(name)
        count, _, ttl = await pipe.execute()
        return float(max(ttl, 1)) if int(count) > limit else None
