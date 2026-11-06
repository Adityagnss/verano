"""
The pytest plugin (loaded automatically once `verano` is installed): a summary of every `verano.test` call and,
with `--verano-report FILE`, a JSON report of them. It only reads what `verano.testing` recorded; it never sends
anything anywhere.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from verano.testing import RECORDER


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("verano")
    group.addoption(
        "--verano-report", metavar="FILE", default=None, help="Write the verano.test results to FILE (JSON)."
    )


def pytest_sessionstart(session: pytest.Session) -> None:
    RECORDER.clear()


def pytest_terminal_summary(terminalreporter: Any, config: pytest.Config) -> None:
    if not RECORDER:
        return
    passed = sum(1 for r in RECORDER if r.passed)
    terminalreporter.write_sep("-", "Verano checks")
    terminalreporter.write_line(f"{len(RECORDER)} cases checked, {passed} passed, {len(RECORDER) - passed} failed.")
    for r in RECORDER:
        if not r.passed:
            terminalreporter.write_line(f"  failed: {r.name}: {'; '.join(r.problems)}")
    terminalreporter.write_line(
        "To run your whole test set on this function from Verano: wrap it with verano.serve(fn) "
        "and register the address with `verano app add`."
    )
    target = config.getoption("--verano-report")
    if target:
        report = {
            "passed": passed,
            "failed": len(RECORDER) - passed,
            "cases": [
                {"name": r.name, "passed": r.passed, "problems": r.problems, "answer": r.answer} for r in RECORDER
            ],
        }
        Path(target).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        terminalreporter.write_line(f"Report written to {target}.")
