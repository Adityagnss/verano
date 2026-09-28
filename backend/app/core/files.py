"""
Safety checks for untrusted uploaded files.

Every uploaded file is treated as hostile until proven otherwise:
- `check_magic` confirms a file really is the format its extension claims (a `.xlsx`
  must be a zip archive, a `.pdf` must start with the PDF signature).
- `check_zip` inspects a zip-based file's directory (XLSX, DOCX) before anything
  decompresses it: too many entries, too much total uncompressed data, or an entry that
  would expand far beyond its compressed size (a "zip bomb") is refused.
- `Deadline` stops a parse that runs longer than the configured time. Readers call
  `check()` as they go (per row, per page), and the worker's hard time limit backs it up
  for a parser stuck inside native code.
"""

import time
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.core.config import Settings
from app.core.errors import AppError

ZIP_SIGNATURE = b"PK\x03\x04"


class UnsafeFile(AppError):
    status_code = 422
    code = "unsafe_file"


class ParseTimeout(AppError):
    status_code = 422
    code = "parse_timeout"


@dataclass(frozen=True)
class ZipLimits:
    max_uncompressed_bytes: int
    max_entries: int
    max_ratio: float


def zip_limits(settings: Settings) -> ZipLimits:
    return ZipLimits(settings.zip_max_uncompressed_bytes, settings.zip_max_entries, settings.zip_max_ratio)


def check_magic(path: Path, signature: bytes | None, label: str) -> None:
    if signature is None:
        return
    with path.open("rb") as handle:
        if handle.read(len(signature)) != signature:
            raise UnsafeFile(f"This file isn't a valid {label} file. Save it again from its app and re-upload.")


def check_zip(path: Path, limits: ZipLimits, label: str) -> None:
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
    except zipfile.BadZipFile as exc:
        raise UnsafeFile(f"This {label} file is damaged and can't be opened.") from exc
    if len(entries) > limits.max_entries:
        raise UnsafeFile(f"This {label} file has too many internal parts ({len(entries):,}).")
    total = sum(entry.file_size for entry in entries)
    if total > limits.max_uncompressed_bytes:
        raise UnsafeFile(
            f"This {label} file expands to {total / 1_000_000:,.0f} MB, over the "
            f"{limits.max_uncompressed_bytes / 1_000_000:,.0f} MB limit."
        )
    for entry in entries:
        if entry.compress_size and entry.file_size / entry.compress_size > limits.max_ratio:
            raise UnsafeFile(f"This {label} file contains a part that expands suspiciously (a possible zip bomb).")


class Deadline:
    def __init__(self, seconds: float, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._seconds = seconds
        self._expires = clock() + seconds

    def check(self) -> None:
        if self._clock() > self._expires:
            raise ParseTimeout(
                f"Reading this file took longer than {self._seconds:g} seconds, so it was stopped. "
                "Try a smaller file or remove unused columns."
            )
