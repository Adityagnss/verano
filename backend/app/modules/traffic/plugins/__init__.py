"""
Import formats (standards 3.1): one adapter per format, registered by name.

An adapter reads the parsed JSON of a file and returns the traces in it plus a plain-words problem for every record
it could not use. It never raises for a bad record and never stores anything: parsing is pure, storing is the
service's job. Adding a format is one new file here; no other code changes.
"""

from collections.abc import Callable
from typing import Any, ClassVar, Protocol, TypeVar

from app.core.registry import Registry
from app.modules.traffic.domain import ParseResult


class ImportAdapter(Protocol):
    name: ClassVar[str]
    label: ClassVar[str]
    hint: ClassVar[str]

    def accepts(self, data: Any) -> bool:
        """Whether this file looks like the format (used when the person leaves the format on automatic)."""
        ...

    def parse(self, data: Any, limit: int) -> ParseResult:
        """The traces in the file, reading at most `limit` records."""
        ...


ADAPTERS: Registry[ImportAdapter] = Registry("import format")
A = TypeVar("A", bound=ImportAdapter)


def adapter(name: str) -> Callable[[type[A]], type[A]]:
    """Registers an instance of the decorated adapter class under its format name."""

    def decorator(cls: type[A]) -> type[A]:
        ADAPTERS.add(name, cls())
        return cls

    return decorator


def records_of(data: Any, keys: tuple[str, ...]) -> list[Any]:
    """The list of records in a file: the file itself when it is a list, or the list under one of the usual keys, or
    the single object."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in keys:
            if isinstance(data.get(key), list):
                found: list[Any] = data[key]
                return found
        return [data]
    return []
