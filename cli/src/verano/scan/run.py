"""Scans a folder: every source file the scanners understand, and the data files that might be test cases."""

from pathlib import Path

from verano.scan import broad_scan, prompt_files, walk
from verano.scan.findings import ScanResult
from verano.scan.python_scan import read_python, scan_source
from verano.scan.ts_scan import SUFFIXES as JS_SUFFIXES
from verano.scan.ts_scan import scan_source as scan_js

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


def _read_bytes(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except OSError:
        return None


def scan(root: Path, include_tests: bool = False) -> ScanResult:
    result = ScanResult()
    for path in walk.source_files(root, {".py", *JS_SUFFIXES, *broad_scan.SUFFIXES}, include_tests):
        relative = path.relative_to(root).as_posix()
        if walk.too_big(path):
            result.files_skipped.append(f"{relative}: larger than 1 MB")
            continue
        try:
            if path.suffix.lower() == ".py":
                source = read_python(path)
                if source is None:
                    result.files_skipped.append(f"{relative}: not UTF-8 text")
                    continue
                findings, other = scan_source(source, relative)
            else:
                data = _read_bytes(path)
                if data is None:
                    result.files_skipped.append(f"{relative}: could not be read")
                    continue
                if path.suffix.lower() in JS_SUFFIXES:
                    findings, other = scan_js(data, relative, path.suffix.lower())
                else:
                    findings, other = broad_scan.scan_source(data, relative, path.suffix.lower())
        except (SyntaxError, ValueError, RecursionError):
            result.files_skipped.append(f"{relative}: could not be parsed")
            continue
        result.files_scanned += 1
        suffix = path.suffix.lower()
        language = (
            "Python"
            if suffix == ".py"
            else "TypeScript/JavaScript"
            if suffix in JS_SUFFIXES
            else broad_scan.language_name(suffix)
        )
        result.by_language[language] = result.by_language.get(language, 0) + 1
        result.findings += findings
        result.other += other
    found, skipped, read = prompt_files.scan_prompt_files(root)
    if read:
        result.files_scanned += read
        result.by_language["prompt files"] = read
        result.findings += found
    result.files_skipped += skipped
    result.data_files = find_data_files(root)
    return result
