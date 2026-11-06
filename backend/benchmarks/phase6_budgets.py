"""
Phase 6 latency budgets (ENGINEERING_STANDARDS section 4b), measured on synthetic data and printed as a table.

Paired bootstrap on 500 cases with 10,000 resamples, judge agreement on 1,000 labels, majority of 1,000 label
lists, and a content-hash cache key per case. Each line is the best of several repeats, so a one-off pause on
the machine does not decide it. No database or network is used.
"""

import hashlib
import json
import os
import platform
import subprocess
import time
from collections.abc import Callable

import numpy as np

from app.modules.evaluation.agreement import agreement, majority
from app.modules.evaluation.significance import RESAMPLES, bootstrap_interval

REPEATS = 5
CASES = 500
LABELS = 1_000
KEYS = 10_000
SEED = 20_260_601


def best_ms(work: Callable[[], object], repeats: int = REPEATS) -> float:
    work()  # warm-up
    best = float("inf")
    for _ in range(repeats):
        began = time.perf_counter()
        work()
        best = min(best, (time.perf_counter() - began) * 1000)
    return best


def machine() -> str:
    cpu = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True).stdout.strip()
    system = f"{platform.system()} {platform.release()}"
    return f"{cpu or platform.processor()} · {os.cpu_count()} cores · {system} · Python {platform.python_version()}"


def main() -> None:
    rng = np.random.default_rng(SEED)
    differences = rng.normal(0.02, 0.15, CASES).tolist()
    pairs = [(bool(a), bool(b)) for a, b in rng.integers(0, 2, size=(LABELS, 2))]
    label_lists = [
        [("good", "bad", "unsure")[i] for i in rng.integers(0, 3, size=int(rng.integers(1, 6)))] for _ in range(LABELS)
    ]
    case = {"input": "My card was charged twice", "expected": "billing", "vars": {"tier": "gold", "n": 3}}

    def bootstrap() -> object:
        return bootstrap_interval(differences, 0.05, SEED)

    def kappa() -> object:
        return agreement(pairs, min_labels=20, raw_threshold=0.8, kappa_threshold=0.6)

    def majorities() -> object:
        return [majority(labels) for labels in label_lists]

    def keys() -> object:
        return [hashlib.sha256(json.dumps(case, sort_keys=True).encode()).hexdigest() for _ in range(KEYS)]

    rows = [
        (f"Paired bootstrap, {CASES} cases x {RESAMPLES:,} resamples", best_ms(bootstrap), 300.0, 1),
        (f"Agreement (kappa), {LABELS:,} labels", best_ms(kappa), 50.0, 1),
        (f"Majority, {LABELS:,} label lists", best_ms(majorities), 50.0, 1),
        (f"Cache key, per call (over {KEYS:,})", best_ms(keys), 5.0, KEYS),
    ]
    print(f"Phase 6 latency budgets · best of {REPEATS} · {machine()}")
    print(f"{'':50}{'measured ms':>13}{'budget ms':>11}  result")
    for label, ms, budget, per in rows:
        measured = ms / per
        print(f"{label:50}{measured:13.3f}{budget:11.1f}  {'PASS' if measured < budget else 'MISS'}")


if __name__ == "__main__":
    main()
