"""
Text embedders for near-duplicate removal (ADR 0007), behind one small interface so a
provider embedding model through the gateway can be dropped in later.

- `fastembed`: a local ONNX sentence-embedding model (the setting `embedding_model`),
  downloaded once into `embedding_cache_dir` (the files volume) and reused offline.
- `lexical`: character-trigram vectors (case and punctuation ignored) hashed into a fixed size. No model and no
  network; used by tests and as an offline fallback. It only catches near-identical
  wording, not paraphrases.
Vectors are L2-normalized, so a dot product is the cosine similarity.
"""

import hashlib
import math
import re
from collections.abc import Callable, Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

from app.core.config import Settings
from app.core.registry import Registry

LEXICAL_DIMENSIONS = 512
PUNCTUATION = re.compile(r"[^\w\s]")


class Embedder(Protocol):
    name: str

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


def _normalized(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


class LexicalEmbedder:
    name = "lexical-trigram"

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            vector = [0.0] * LEXICAL_DIMENSIONS
            padded = f"  {' '.join(PUNCTUATION.sub(' ', text.lower()).split())}  "
            for index in range(len(padded) - 2):
                digest = hashlib.blake2b(padded[index : index + 3].encode(), digest_size=4).digest()
                vector[int.from_bytes(digest) % LEXICAL_DIMENSIONS] += 1.0
            vectors.append(_normalized(vector))
        return vectors


@lru_cache(maxsize=2)
def _fastembed_model(model: str, cache_dir: Path) -> Any:
    from fastembed import TextEmbedding

    return TextEmbedding(model, cache_dir=str(cache_dir))


class FastEmbedder:
    def __init__(self, model: str, cache_dir: Path) -> None:
        self.name = model
        self._model = model
        self._cache_dir = cache_dir

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        model = _fastembed_model(self._model, self._cache_dir)
        return [_normalized([float(value) for value in vector]) for vector in model.embed(list(texts))]


EMBEDDERS: Registry[Callable[[Settings], Embedder]] = Registry("embedder")
EMBEDDERS.add("lexical", lambda _: LexicalEmbedder())
EMBEDDERS.add("fastembed", lambda settings: FastEmbedder(settings.embedding_model, settings.embedding_cache_dir))


def build_embedder(settings: Settings) -> Embedder:
    return EMBEDDERS[settings.embedder](settings)
