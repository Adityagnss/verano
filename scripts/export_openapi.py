"""
Write the backend's OpenAPI schema to a file without starting a server.

The frontend's API types are generated from this file (`make api-client`), so they can
never drift from the backend's real request and response shapes. Run from backend/:
`uv run python ../scripts/export_openapi.py <output.json>`.
"""

import json
import sys
from pathlib import Path

from app.core.config import Settings
from app.main import create_app


def main() -> int:
    target = Path(sys.argv[1])
    schema = create_app(Settings(_env_file=None)).openapi()
    target.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
    print(f"Wrote {target} ({len(schema['paths'])} paths)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
