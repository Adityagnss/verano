"""Scans a folder: every source file the scanners understand, and the data files that might be test cases."""

from pathlib import Path

from verano.scan import walk
from verano.scan.findings import ScanResult
from verano.scan.python_scan import read_python, scan_source

DATA_DIRS = {"data", "fixtures", "examples", "samples", "datasets", "testdata"}
DATA_SUFFIXES = {".csv", ".tsv", ".jsonl", ".ndjson"}
MAX_DATA_FILES = 8


def find_data_files(root: Path) -> list[str]:
    """Tables in folders named like test data: candidates for `data.cases`, shown but never wired in."""
    found: list[str] = []
    for path in walk.source_files(root, DATA_SUFFIXES):
        relative = path.relative_to(root)
        if any(part.lower() in DATA_DIRS for part in relative.parts[:-1]) and not walk.too_big(path):
            found.append(relative.as_posix())
        if len(found) >= MAX_DATA_FILES:
            break
    return found


def scan(root: Path, include_tests: bool = False) -> ScanResult:
    result = ScanResult()
    for path in walk.source_files(root, {".py"}, include_tests):
        relative = path.relative_to(root).as_posix()
        if walk.too_big(path):
            result.files_skipped.append(f"{relative}: larger than 1 MB")
            continue
        source = read_python(path)
        if source is None:
            result.files_skipped.append(f"{relative}: not UTF-8 text")
            continue
        try:
            findings, other = scan_source(source, relative)
        except (SyntaxError, ValueError, RecursionError):
            result.files_skipped.append(f"{relative}: Python could not parse it")
            continue
        result.files_scanned += 1
        result.findings += findings
        result.other += other
    result.data_files = find_data_files(root)
    return result
