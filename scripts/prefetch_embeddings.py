"""
Pre-fetch the embedding model so an air-gapped install never needs the internet (backlog M8.5).

Run it once on a machine that can reach the model host (`python scripts/prefetch_embeddings.py`). It downloads the model
named by the setting `embedding_model` into `embedding_cache_dir`, the folder the app reads from, and then loads it once
offline to prove the files are complete. Copy that folder to the air-gapped host's files volume. Options:
`--model NAME` and `--cache-dir PATH` override the settings.
"""

import argparse
import sys
from pathlib import Path

from app.core.config import get_settings


def main() -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=settings.embedding_model)
    parser.add_argument("--cache-dir", type=Path, default=settings.embedding_cache_dir)
    args = parser.parse_args()
    try:
        from fastembed import TextEmbedding
    except ImportError:
        print("fastembed is not installed here. Install the backend dependencies first (`uv sync`).", file=sys.stderr)
        return 1
    args.cache_dir.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {args.model} into {args.cache_dir} …")
    try:
        model = TextEmbedding(args.model, cache_dir=str(args.cache_dir))
        vector = next(iter(model.embed(["check"])))
    except Exception as error:
        print(f"Could not fetch or load the model: {error}", file=sys.stderr)
        return 1
    print(f"Done. The model loads and gives {len(vector)}-number vectors. Copy {args.cache_dir} to the offline host.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
