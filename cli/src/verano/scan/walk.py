"""Which files a scan reads: source files in the folder, without dependencies, caches or builds."""

import os
import re
from collections.abc import Iterator
from pathlib import Path

SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", ".venv", "venv", "env", "__pycache__", ".tox", ".nox", "site-packages",
    "dist", "build", ".next", ".nuxt", "target", "vendor", ".mypy_cache", ".ruff_cache", ".pytest_cache", ".idea",
    ".vscode", "coverage", ".cache", ".gradle", "Pods", "obj", ".build", "DerivedData",
}  # fmt: skip
TEST_DIRS = {"tests", "test", "__tests__", "spec", "specs", "Tests", "androidTest", "__mocks__"}
TEST_FILE = re.compile(r"(_test\.go|Tests?\.(java|kt|swift|cs)|_spec\.rb|Test\.php|\.(test|spec)\.[jt]sx?)$")
MAX_BYTES = 1_000_000
MAX_FILES = 20_000


def source_files(root: Path, suffixes: set[str], include_tests: bool = True) -> Iterator[Path]:
    """Files with one of `suffixes`, in a stable order, without descending into skipped folders or links."""
    seen = 0
    for folder, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(
            d
            for d in dirs
            if d not in SKIP_DIRS and not d.endswith(".egg-info") and (include_tests or d not in TEST_DIRS)
        )
        for name in sorted(files):
            path = Path(folder) / name
            if (
                path.suffix.lower() in suffixes
                and not path.is_symlink()
                and (include_tests or not TEST_FILE.search(name))
            ):
                seen += 1
                if seen > MAX_FILES:
                    return
                yield path


def too_big(path: Path) -> bool:
    try:
        return path.stat().st_size > MAX_BYTES
    except OSError:
        return True
