"""`verano init`: what it writes, what it refuses to overwrite, and that its file always loads."""

import io
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.conftest import Run
from verano import init
from verano.errors import CliError
from verano.loader import load
from verano.scan.findings import Finding, to_entry
from verano.scan.render import render

APP = """
import openai

SYSTEM = "You are a support agent.\\nReply with one word: billing, shipping or technical."

def classify_ticket(ticket):
    return client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0,
        messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": f"Ticket: {ticket}"}],
    )

def merge(a, b):
    return client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": f"{a} / {b}"}])

def dynamic(messages):
    return client.chat.completions.create(model="gpt-4o", messages=messages)
"""


def project(tmp_path: Path) -> Path:
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "support.py").write_text(APP)
    return tmp_path


def finding(system: str | None, user: str | None, variables: list[str] | None = None, **extra: object) -> Finding:
    return Finding("app/p.py", 3, system=system, user=user, variables=variables or [], **extra)  # type: ignore[arg-type]


NASTY = [
    "Plain.",
    "Line one\nLine two: with a colon\n# not a comment\n- not a list",
    "  leading spaces and \"quotes\" and 'apostrophes'",
    "Tabs\tinside\nand more",
    "Unicode: zoë, 日本語, 🙂\nsecond",
    "Braces: {{ '{{' }} and {% x %} written as literals",
    "ends with a colon:",
    "key: value\nother: value2",
    "| pipe\n> fold\n& anchor\n* alias",
    "trailing   \nspaces   ",
    "'single' and \"double\"\n\\ backslash",
]


@pytest.mark.parametrize("text", NASTY)
def test_whatever_the_prompt_says_the_written_file_loads_and_gives_the_same_text(tmp_path: Path, text: str) -> None:
    entry = to_entry(finding(text, "User: {{ attachment }} ok", ["attachment"], model="gpt-4o"), set())
    path = tmp_path / "verano.yaml"
    path.write_text(render("my project: v2", [entry], []))
    (prompt,) = load(path).prompts
    assert prompt.system == text.strip()
    assert prompt.user == "User: {{ attachment }} ok"
    assert prompt.entry.models == ["gpt-4o"]
    assert load(path).file.project == "my project: v2"


def test_a_file_without_a_found_model_or_a_provider_still_loads_and_says_what_to_fill_in(tmp_path: Path) -> None:
    entry = to_entry(finding("Do it.", None), set())
    path = tmp_path / "verano.yaml"
    path.write_text(render("x", [entry], []))
    loaded = load(path)
    assert loaded.prompts[0].entry.models == ["TODO-model"]
    assert any("still has TODO values" in w for w in loaded.warnings)
    assert "# keys:" in path.read_text()


def test_unticked_entries_stay_in_the_file_as_comments_with_their_reason(tmp_path: Path) -> None:
    ticked = to_entry(finding("A.", None, provider="anthropic", model="claude-3-5-haiku"), set())
    skipped = to_entry(finding("B {{ a }} {{ b }}", None, ["a", "b"]), {ticked.name})
    text = render("x", [ticked], [skipped])
    assert "  anthropic: env:ANTHROPIC_API_KEY" in text
    assert "# Not included: " in text
    assert "it has 2 inputs (a, b)" in text
    assert all(line.startswith("  #") or not line.strip() for line in text.split("# Not included")[1].splitlines()[1:])
    path = tmp_path / "verano.yaml"
    path.write_text(text)
    assert len(load(path).prompts) == 1


def test_init_writes_a_loadable_file_ticks_what_can_run_and_keeps_the_rest_as_comments(
    run: Run, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = project(tmp_path)
    monkeypatch.chdir(root)
    result = run("init", "--yes")
    assert result.code == 0, result.err
    for line in (
        "Scanned 1 file (1 Python).",
        "Found 3 prompts; could not read 1.",
        "[x]  1  classify-ticket",
        "app/support.py:7",
        "openai · gpt-4o-mini · temperature 0 · 1 input",
        "[ ]  2  merge",
        "not ready: it has 2 inputs (a, b)",
        "[ ]  3  dynamic",
        "the messages come from `messages`",
        "Wrote ",
    ):
        assert line in result.err, line
    loaded = load(root / "verano.yaml")
    (prompt,) = loaded.prompts
    assert prompt.entry.name == "classify-ticket"
    assert prompt.system == "You are a support agent.\nReply with one word: billing, shipping or technical."
    assert prompt.user == "Ticket: {{ attachment }}"
    assert prompt.entry.params.given() == {"temperature": 0}
    assert prompt.entry.source is not None
    assert (prompt.entry.source.file, prompt.entry.source.line) == ("app/support.py", 7)
    text = (root / "verano.yaml").read_text()
    assert "# `ticket` is now `attachment`" in text
    assert "# Not included: merge (app/support.py:14)" in text
    assert "dynamic" in text
    assert "openai: env:OPENAI_API_KEY" in text


def test_it_never_overwrites_unless_told_to_and_can_print_or_write_elsewhere(
    run: Run, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = project(tmp_path)
    monkeypatch.chdir(root)
    (root / "verano.yaml").write_text("keep me\n")
    refused = run("init", "--yes")
    assert refused.code == 1
    assert "verano.yaml already exists" in refused.err
    assert (root / "verano.yaml").read_text() == "keep me\n"
    shown = run("init", "--yes", "--print")
    assert shown.code == 0
    assert shown.out.startswith("# verano.yaml, proposed by `verano init`")
    assert (root / "verano.yaml").read_text() == "keep me\n"
    other = run("init", "--yes", "-o", "proposed.yaml")
    assert other.code == 0
    assert (root / "proposed.yaml").exists()
    assert run("init", "--yes", "--force").code == 0
    assert (root / "verano.yaml").read_text().startswith("# verano.yaml")


def test_nothing_found_and_a_bad_folder_are_said_plainly(
    run: Run, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "plain.py").write_text("print('hello')\n")
    monkeypatch.chdir(tmp_path)
    result = run("init", "--yes")
    assert result.code == 0
    assert "No LLM calls with a prompt were found." in result.err
    assert not (tmp_path / "verano.yaml").exists()
    missing = run("init", "nowhere")
    assert missing.code == 1
    assert "is not a folder" in missing.err


def test_the_choice_accepts_numbers_all_or_none_and_refuses_anything_else() -> None:
    default = {0, 2}
    assert init.parse_choice("", 3, default) == default
    assert init.parse_choice(" ALL ", 3, default) == default
    assert init.parse_choice("none", 3, default) == set()
    assert init.parse_choice("1, 2 3", 3, default) == {0, 1, 2}
    for bad in ("4", "0", "x", "1;2"):
        with pytest.raises(CliError, match="not one of the numbers 1 to 3"):
            init.parse_choice(bad, 3, default)


def test_a_person_can_pick_entries_and_one_that_could_not_be_read_is_left_out_with_a_reason(
    run: Run, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = project(tmp_path)
    monkeypatch.chdir(root)
    tty = SimpleNamespace(stdin=io.StringIO(), stderr=io.StringIO())
    tty.stdin.isatty = lambda: True
    tty.stderr.isatty = lambda: True
    monkeypatch.setattr(init, "sys", tty)
    monkeypatch.setattr("typer.prompt", lambda *a, **k: "2,3")
    result = run("init")
    assert result.code == 0
    assert "merge: ready" not in result.err
    assert "dynamic: left out, it could not be read" in result.err
    loaded = load(root / "verano.yaml")
    assert [p.entry.name for p in loaded.prompts] == ["merge"]
    monkeypatch.setattr("typer.prompt", lambda *a, **k: "none")
    nothing = run("init", "--force")
    assert "Nothing was ticked, so no file was written." in nothing.err


def test_test_data_that_might_be_cases_is_suggested_but_never_wired_in(
    run: Run, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = project(tmp_path)
    (root / "data").mkdir()
    (root / "data" / "tickets.csv").write_text("ticket,expected\na,b\n")
    monkeypatch.chdir(root)
    result = run("init", "--yes")
    assert "possible test data: data/tickets.csv" in result.err
    assert "tickets.csv" not in (root / "verano.yaml").read_text().replace("data/examples.csv", "")
