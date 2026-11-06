"""
Checks that the API did not break its promise (ADR 0022).

    cd backend && PYTHONPATH=. uv run python ../scripts/check_api_compat.py            # compare with the baseline
    cd backend && PYTHONPATH=. uv run python ../scripts/check_api_compat.py --update   # record the current API

The baseline is the API of the last release (`docs/api/baseline.json`). A removal, a newly required field or a
field that no longer comes back fails the check; additions and deprecated routes do not. After a release, or when
a breaking change was announced and its window has passed, run it with --update and commit the new baseline.
"""

import json
import sys
from pathlib import Path

from app.core.apicompat import breaking_changes, signature
from app.main import create_app

BASELINE = Path(__file__).resolve().parents[1] / "docs" / "api" / "baseline.json"


def main() -> int:
    current = signature(create_app().openapi())
    if "--update" in sys.argv:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(json.dumps(current, indent=1, sort_keys=True) + "\n")
        print(f"Recorded {len(current)} routes in {BASELINE}.")
        return 0
    if not BASELINE.exists():
        print(f"No baseline at {BASELINE}. Run with --update to record the current API.")
        return 1
    problems = breaking_changes(json.loads(BASELINE.read_text()), current)
    for problem in problems:
        print(problem)
    print(f"{len(problems)} breaking change(s) against the baseline ({len(current)} routes now).")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
