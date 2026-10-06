"""
Check 5.3 (DEVELOPMENT.md, H5): does near-duplicate removal catch real near-copies with the
real embedding model, and leave distinct cases alone?

It embeds examples/near-duplicates/cases.csv with the embedder set in the settings (fastembed
by default, downloaded once into the cache dir) and feeds the rows, in file order, through the
generator's own `near_duplicates` rule at the configured `dedupe_similarity`. The file holds
10 planted pairs (the second copy of each comes last) and 20 distinct tickets on the same
topics. Pass: at least 9 of the 10 second copies are dropped and at most 1 distinct ticket is.
No model call, no cost. Run from backend/: `PYTHONPATH=. uv run python ../scripts/check_dedupe.py`.
"""

import csv
import sys
from pathlib import Path

from app.core.config import Settings
from app.modules.generator.domain import near_duplicates
from app.modules.generator.plugins.embedders import build_embedder

CASES = Path(__file__).resolve().parents[1] / "examples" / "near-duplicates" / "cases.csv"


def main() -> int:
    settings = Settings()
    rows = list(csv.DictReader(CASES.open()))
    embedder = build_embedder(settings)
    vectors = embedder.embed([row["ticket"] for row in rows])
    dropped = set(near_duplicates([], vectors, settings.dedupe_similarity))

    seen: set[str] = set()
    caught = missed = wrongly_dropped = 0
    for index, row in enumerate(rows):
        group, gone = row["group"], index in dropped
        if group == "distinct" or group not in seen:
            seen.add(group)
            if gone:
                wrongly_dropped += 1
                print(f"  dropped a distinct case: {row['ticket']}")
        elif gone:
            caught += 1
        else:
            missed += 1
            other = next(j for j, r in enumerate(rows) if r["group"] == group)
            score = sum(a * b for a, b in zip(vectors[index], vectors[other], strict=True))
            print(f"  kept a near-copy ({group}, similarity {score:.3f}): {row['ticket']}")

    passed = caught >= 9 and wrongly_dropped <= 1
    print(
        f"embedder {embedder.name}, threshold {settings.dedupe_similarity}: "
        f"{caught}/10 near-copies dropped, {wrongly_dropped}/20 distinct dropped "
        f"(dropped_duplicates would be {len(dropped)}) -> {'PASS' if passed else 'FAIL'}"
    )
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
