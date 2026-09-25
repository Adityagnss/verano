"""
Generic plugin registry.

The one extension mechanism used across modules (providers, evaluators, task types,
failure taggers, candidate strategies, storage backends, mock behaviors). A plugin class
registers itself under a name with a decorator; callers look it up by name, so adding a
plugin never edits a branch. `load_plugins` imports every module of a plugins package so
their decorators run; each module's service calls it once for its own package.
"""

import importlib
import pkgutil
from collections.abc import Callable, Iterator
from typing import Generic, TypeVar

from app.core.errors import NotFound

T = TypeVar("T")


class Registry(Generic[T]):
    def __init__(self, kind: str) -> None:
        self.kind = kind
        self._items: dict[str, T] = {}

    def register(self, name: str) -> Callable[[T], T]:
        def decorator(item: T) -> T:
            self.add(name, item)
            return item

        return decorator

    def add(self, name: str, item: T) -> None:
        if name in self._items:
            raise ValueError(f"{self.kind} '{name}' is already registered")
        self._items[name] = item

    def __getitem__(self, name: str) -> T:
        try:
            return self._items[name]
        except KeyError as exc:
            raise NotFound(f"Unknown {self.kind}: '{name}'.", {"known": sorted(self._items)}) from exc

    def __contains__(self, name: object) -> bool:
        return name in self._items

    def __iter__(self) -> Iterator[str]:
        return iter(self._items)

    def items(self) -> list[tuple[str, T]]:
        return list(self._items.items())


def load_plugins(package: str) -> None:
    module = importlib.import_module(package)
    for info in pkgutil.iter_modules(module.__path__):
        importlib.import_module(f"{package}.{info.name}")
