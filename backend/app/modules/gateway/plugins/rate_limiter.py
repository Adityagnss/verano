"""
Valkey-backed rate limiter: a request bucket and a token bucket per credential.

Buckets live in Valkey so every API process and worker shares one view of each key's
budget. Acquisition is one atomic Lua script that refills both buckets from elapsed time,
honours a shared cooldown set after a 429 (so all workers back off together, not just the
one that was throttled), and either takes the slot or returns how long to wait.
The rates themselves adapt: `record_success` and `record_throttle` feed provider headers
and 429s through the pure AIMD rules in `gateway.domain` and store the result.
"""

import asyncio
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from redis.asyncio import Redis

from app.core.errors import RateLimited
from app.modules.gateway.domain import (
    AdaptiveLimit,
    AdaptivePolicy,
    RateHeaders,
    after_success,
    after_throttle,
    resolve_ceiling,
    start_limit,
)
from app.modules.registry.schemas import CallTarget

MS_PER_MINUTE = 60_000.0

ACQUIRE_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local rpm = tonumber(ARGV[2])
local tpm = tonumber(ARGV[3])
local cost = tonumber(ARGV[4])
local ttl = tonumber(ARGV[5])
local state = redis.call('HMGET', key, 'r', 't', 'ts', 'cooldown')
local r = tonumber(state[1]) or rpm
local t = tonumber(state[2]) or tpm
local ts = tonumber(state[3]) or now
local cooldown = tonumber(state[4]) or 0
if cooldown > now then
  return tostring(cooldown - now)
end
local elapsed = math.max(0, now - ts)
r = math.min(rpm, r + elapsed * rpm / 60000.0)
t = math.min(tpm, t + elapsed * tpm / 60000.0)
local need_t = math.min(cost, tpm)
if r >= 1 and t >= need_t then
  redis.call('HSET', key, 'r', r - 1, 't', t - cost, 'ts', now)
  redis.call('PEXPIRE', key, ttl)
  return '0'
end
redis.call('HSET', key, 'r', r, 't', t, 'ts', now)
redis.call('PEXPIRE', key, ttl)
local wait_r = 0
if r < 1 then wait_r = (1 - r) * 60000.0 / rpm end
local wait_t = 0
if t < need_t then wait_t = (need_t - t) * 60000.0 / tpm end
return tostring(math.max(wait_r, wait_t))
"""


def _text(value: bytes | str) -> str:
    return value.decode() if isinstance(value, bytes) else value


@dataclass(frozen=True)
class EffectiveLimits:
    rpm: AdaptiveLimit
    tpm: AdaptiveLimit


class ValkeyRateLimiter:
    def __init__(
        self,
        valkey: Redis,
        policy: AdaptivePolicy,
        acquire_timeout_s: float,
        state_ttl_s: int,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        now_ms: Callable[[], float] = lambda: time.time() * 1000,
    ) -> None:
        self._valkey = valkey
        self._policy = policy
        self._timeout_ms = acquire_timeout_s * 1000
        self._ttl_ms = state_ttl_s * 1000
        self._sleep = sleep
        self._now_ms = now_ms
        self._acquire = valkey.register_script(ACQUIRE_SCRIPT)

    @staticmethod
    def _bucket_key(credential_id: uuid.UUID) -> str:
        return f"rl:{credential_id}:bucket"

    @staticmethod
    def _adapt_key(credential_id: uuid.UUID) -> str:
        return f"rl:{credential_id}:adapt"

    async def limits(self, target: CallTarget) -> EffectiveLimits:
        raw = await self._valkey.hgetall(self._adapt_key(target.credential_id))
        values = {_text(k): float(v) for k, v in raw.items()}
        rpm = self._load(values, "rpm", target.default_limits.rpm, target.override_rpm)
        tpm = self._load(values, "tpm", target.default_limits.tpm, target.override_tpm)
        return EffectiveLimits(rpm=rpm, tpm=tpm)

    async def acquire(self, target: CallTarget, tokens: int) -> float:
        limits = await self.limits(target)
        waited_ms = 0.0
        while True:
            wait_ms = float(
                await self._acquire(
                    keys=[self._bucket_key(target.credential_id)],
                    args=[self._now_ms(), limits.rpm.current, limits.tpm.current, tokens, self._ttl_ms],
                )
            )
            if wait_ms <= 0:
                return waited_ms
            if waited_ms + wait_ms > self._timeout_ms:
                raise RateLimited(
                    f"{target.provider_display_name} rate limits kept this call waiting too long. Try again later.",
                    {"waited_ms": waited_ms},
                )
            await self._sleep(wait_ms / 1000)
            waited_ms += wait_ms

    async def record_success(self, target: CallTarget, headers: RateHeaders, estimated: int, actual: int) -> None:
        limits = await self.limits(target)
        rpm = after_success(
            limits.rpm, target.default_limits.rpm, target.override_rpm, headers.limit_requests, self._policy
        )
        tpm = after_success(
            limits.tpm, target.default_limits.tpm, target.override_tpm, headers.limit_tokens, self._policy
        )
        pipe = self._valkey.pipeline(transaction=False)
        pipe.hset(self._adapt_key(target.credential_id), items=self._dump(rpm, tpm))
        pipe.pexpire(self._adapt_key(target.credential_id), int(self._ttl_ms))
        pipe.hincrbyfloat(self._bucket_key(target.credential_id), "t", estimated - actual)
        await pipe.execute()

    async def record_throttle(self, target: CallTarget, retry_after_s: float | None) -> None:
        limits = await self.limits(target)
        rpm, tpm = after_throttle(limits.rpm, self._policy), after_throttle(limits.tpm, self._policy)
        pipe = self._valkey.pipeline(transaction=False)
        pipe.hset(self._adapt_key(target.credential_id), items=self._dump(rpm, tpm))
        pipe.pexpire(self._adapt_key(target.credential_id), int(self._ttl_ms))
        if retry_after_s:
            pipe.hset(self._bucket_key(target.credential_id), "cooldown", self._now_ms() + retry_after_s * 1000)
        await pipe.execute()

    @staticmethod
    def _load(values: dict[str, float], name: str, default: int, override: int | None) -> AdaptiveLimit:
        if f"{name}_current" not in values:
            return start_limit(default, override)
        learned = values.get(f"{name}_learned")
        ceiling = resolve_ceiling(default, override, learned)
        return AdaptiveLimit(ceiling=ceiling, current=min(values[f"{name}_current"], ceiling), learned=learned)

    @staticmethod
    def _dump(rpm: AdaptiveLimit, tpm: AdaptiveLimit) -> list[str | float]:
        values = {"rpm_current": rpm.current, "tpm_current": tpm.current}
        values.update(
            {f"{name}_learned": limit.learned for name, limit in (("rpm", rpm), ("tpm", tpm)) if limit.learned}
        )
        return [part for pair in values.items() for part in pair]
