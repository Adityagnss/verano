"""
Live progress for long-running work, shared by every feature (uploads now, generation and
experiments later): one mechanism, streamed to the browser over Server-Sent Events.

A job publishes `ProgressEvent`s to a channel. Each event is stored as the channel's
latest snapshot in Valkey (with a TTL) and broadcast with Valkey pub/sub. A reader
subscribes first and then reads the snapshot, so it can't miss an event published in
between; it gets the current state immediately and every change after it, and the stream
ends when a terminal event (succeeded or failed) arrives. Keepalive ticks (`None`) let the
SSE layer hold idle connections open through proxies.
"""

from collections.abc import AsyncIterator
from enum import StrEnum

from pydantic import BaseModel
from redis.asyncio import Redis


class ProgressStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ProgressEvent(BaseModel):
    stage: str
    status: ProgressStatus
    processed: int = 0
    total: int | None = None
    message: str | None = None

    @property
    def terminal(self) -> bool:
        return self.status is not ProgressStatus.RUNNING


class ProgressHub:
    def __init__(self, valkey: Redis, ttl_s: int) -> None:
        self._valkey = valkey
        self._ttl_s = ttl_s

    @staticmethod
    def _snapshot_key(channel: str) -> str:
        return f"progress:{channel}:latest"

    @staticmethod
    def _events_key(channel: str) -> str:
        return f"progress:{channel}:events"

    async def publish(self, channel: str, event: ProgressEvent) -> None:
        payload = event.model_dump_json()
        pipe = self._valkey.pipeline(transaction=False)
        pipe.set(self._snapshot_key(channel), payload, ex=self._ttl_s)
        pipe.publish(self._events_key(channel), payload)
        await pipe.execute()

    async def snapshot(self, channel: str) -> ProgressEvent | None:
        raw = await self._valkey.get(self._snapshot_key(channel))
        return ProgressEvent.model_validate_json(raw) if raw else None

    async def stream(self, channel: str, keepalive_s: float) -> AsyncIterator[ProgressEvent | None]:
        async with self._valkey.pubsub() as pubsub:
            await pubsub.subscribe(self._events_key(channel))
            current = await self.snapshot(channel)
            if current is not None:
                yield current
                if current.terminal:
                    return
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=keepalive_s)
                if message is None:
                    yield None
                    continue
                event = ProgressEvent.model_validate_json(message["data"])
                yield event
                if event.terminal:
                    return
