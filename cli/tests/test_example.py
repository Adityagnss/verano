"""The example project must keep working: it is the first thing a new user runs."""

from pathlib import Path

import pytest

from tests.conftest import Run
from verano.loader import load
from verano.scan.findings import to_entry
from verano.scan.run import scan

EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "support-triage"
pytestmark = pytest.mark.skipif(not EXAMPLE.exists(), reason="the examples folder is not part of the installed package")


@pytest.mark.parametrize("name", ["verano.yaml", "verano.ollama.yaml"])
def test_both_example_files_are_valid_and_point_at_real_data(name: str) -> None:
    loaded = load(EXAMPLE / name)
    (prompt,) = loaded.prompts
    assert prompt.entry.name == "classify-ticket"
    assert prompt.cases is not None
    assert len(prompt.cases.cases) == 100
    assert prompt.cases.skipped == []
    assert {c.expected for c in prompt.cases.cases} == {"billing", "shipping", "technical"}


def test_the_example_file_still_says_what_init_finds_in_the_example_app() -> None:
    result = scan(EXAMPLE)
    entries = {e.name: e for e in (to_entry(f, set()) for f in result.findings)}
    assert set(entries) == {"classify-ticket", "draft-reply"}
    assert entries["classify-ticket"].runnable
    assert not entries["draft-reply"].runnable
    assert entries["draft-reply"].reason is not None
    assert "2 inputs (tone, ticket)" in entries["draft-reply"].reason
    (prompt,) = load(EXAMPLE / "verano.yaml").prompts
    assert prompt.system == entries["classify-ticket"].system
    assert prompt.user == entries["classify-ticket"].user
    assert prompt.entry.params.given() == entries["classify-ticket"].finding.params
    assert prompt.entry.models[0] == entries["classify-ticket"].finding.model


def test_the_readme_commands_exist(run: Run) -> None:
    text = (EXAMPLE / "README.md").read_text()
    for command in ("login", "init", "validate", "push", "run", "status"):
        assert f"verano {command}" in text
        assert run(command, "--help").code == 0
