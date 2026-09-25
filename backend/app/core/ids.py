"""
Identifier generation.

Every primary key is a UUIDv7: time-ordered, so keyset pagination by id follows creation
order and experiment ids can double as the range-partition key for per-experiment tables
(see ADR 0005). Within one millisecond a 12-bit counter keeps ids strictly increasing
(RFC 9562, method 1). Deterministic ids (UUIDv5 over the identifying parts) are used where a
retry or re-plan must produce the same row, such as one TestCaseRun per matrix cell.
"""

import os
import threading
import time
import uuid

DETERMINISTIC_NAMESPACE = uuid.UUID("6f1c6b0e-6a55-4d8e-9a53-1f0f3c2b7a11")
COUNTER_BITS = 12
COUNTER_MAX = (1 << COUNTER_BITS) - 1


class _Uuid7Generator:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last_ms = 0
        self._counter = 0

    def next(self) -> uuid.UUID:
        with self._lock:
            millis = max(time.time_ns() // 1_000_000, self._last_ms)
            if millis == self._last_ms and self._counter < COUNTER_MAX:
                self._counter += 1
            elif millis == self._last_ms:
                millis += 1
                self._counter = 0
            else:
                self._counter = int.from_bytes(os.urandom(1), "big")
            self._last_ms = millis
            counter = self._counter
        tail = int.from_bytes(os.urandom(8), "big") & ((1 << 62) - 1)
        value = (millis & ((1 << 48) - 1)) << 80 | 0x7 << 76 | counter << 64 | 0b10 << 62 | tail
        return uuid.UUID(int=value)


_generator = _Uuid7Generator()


def uuid7() -> uuid.UUID:
    return _generator.next()


def deterministic_id(*parts: object) -> uuid.UUID:
    return uuid.uuid5(DETERMINISTIC_NAMESPACE, "\x1f".join(str(part) for part in parts))
