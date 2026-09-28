"""
File storage for uploads and exports.

`Storage` is the contract; backends register in `STORAGE_BACKENDS` and `VERANO_STORAGE_BACKEND`
picks one (only `local` in Phase 2; the interface is what an S3-compatible backend will
implement). Writes stream in chunks to a temporary file, count bytes and hash as they go,
refuse anything over the size limit, and appear under their key only when complete (an
atomic rename), so a failed or oversized upload never leaves a partial file behind.
Parsers read through `local_path`, which for a remote backend would download to a
temporary file first.
"""

import hashlib
import os
import shutil
import tempfile
import uuid
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import anyio

from app.core.config import Settings
from app.core.errors import AppError
from app.core.registry import Registry

CHUNK_BYTES = 1024 * 1024


class FileTooLarge(AppError):
    status_code = 413
    code = "file_too_large"


@dataclass(frozen=True)
class StoredObject:
    key: str
    size_bytes: int
    sha256: str


class Storage(Protocol):
    async def write_stream(self, key: str, chunks: AsyncIterator[bytes], max_bytes: int) -> StoredObject: ...

    def local_path(self, key: str) -> AbstractAsyncContextManager[Path]: ...

    async def delete_prefix(self, prefix: str) -> None: ...


STORAGE_BACKENDS: Registry[type["LocalStorage"]] = Registry("storage backend")


def too_large_message(max_bytes: int) -> str:
    return f"This file is larger than the {max_bytes / 1_000_000:.0f} MB limit. Split it or remove unused columns."


@STORAGE_BACKENDS.register("local")
class LocalStorage:
    def __init__(self, settings: Settings) -> None:
        self._root = settings.storage_root.resolve()

    def _path(self, key: str) -> Path:
        path = (self._root / key).resolve()
        if not path.is_relative_to(self._root):
            raise ValueError(f"storage key escapes the storage root: {key!r}")
        return path

    async def write_stream(self, key: str, chunks: AsyncIterator[bytes], max_bytes: int) -> StoredObject:
        target = self._path(key)
        handle, temp_name = await anyio.to_thread.run_sync(self._open_temp, target.parent)
        digest, size = hashlib.sha256(), 0
        try:
            with os.fdopen(handle, "wb") as temp:
                async for chunk in chunks:
                    size += len(chunk)
                    if size > max_bytes:
                        raise FileTooLarge(too_large_message(max_bytes), {"max_bytes": max_bytes})
                    digest.update(chunk)
                    await anyio.to_thread.run_sync(temp.write, chunk)
            await anyio.to_thread.run_sync(os.replace, temp_name, target)
        except BaseException:
            await anyio.to_thread.run_sync(lambda: Path(temp_name).unlink(missing_ok=True))
            raise
        return StoredObject(key=key, size_bytes=size, sha256=digest.hexdigest())

    @staticmethod
    def _open_temp(directory: Path) -> tuple[int, str]:
        directory.mkdir(parents=True, exist_ok=True)
        return tempfile.mkstemp(dir=directory, prefix=f".{uuid.uuid4().hex}-")

    @asynccontextmanager
    async def local_path(self, key: str) -> AsyncIterator[Path]:
        yield self._path(key)

    async def delete_prefix(self, prefix: str) -> None:
        await anyio.to_thread.run_sync(lambda: shutil.rmtree(self._path(prefix), ignore_errors=True))


def build_storage(settings: Settings) -> Storage:
    return STORAGE_BACKENDS[settings.storage_backend](settings)
