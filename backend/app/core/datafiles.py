"""
Typed loading of YAML data files.

Configuration that is data rather than environment (provider catalog, model overrides,
evaluator catalog, test-case categories, mock model behavior) lives in YAML next to the
module that owns it. Every file is validated into a Pydantic model at load time, so a
malformed file fails at startup with a precise message instead of deep inside a request.
"""

from functools import lru_cache
from pathlib import Path
from typing import TypeVar

import yaml
from pydantic import BaseModel

M = TypeVar("M", bound=BaseModel)


@lru_cache(maxsize=64)
def _read_yaml(path: Path) -> object:
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def load_yaml(path: Path, model: type[M]) -> M:
    return model.model_validate(_read_yaml(path))
