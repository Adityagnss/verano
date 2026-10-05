"""verano.yaml: what is accepted, what is refused and how clearly."""

import os
from pathlib import Path

import pytest

from verano.errors import CliError
from verano.loader import SEPARATOR, SpecError, find_file, load, normalize_text

VALID = """\
version: 1
project: support-bot
keys:
  openai: env:OPENAI_API_KEY
prompts:
  - name: classify-ticket
    source: {file: app/classify.py, line: 42}
    system: |
      Classify the ticket as billing, shipping or technical.
    params: {temperature: 0, seed: 7, stop: ["END", "END", ""]}
    task:
      type: classification
      goal: Label each support ticket
      allowed_outputs: [billing, shipping, technical]
    data:
      golden: data/golden.csv
      inputs: ["tickets/*.txt"]
    models: [gpt-4o-mini, claude-haiku]
    runs: 3
    budget: 2.5
"""


def write(tmp_path: Path, text: str = VALID, name: str = "verano.yaml") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def project(tmp_path: Path) -> Path:
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "golden.csv").write_text("ticket,expected\nhi,billing\n")
    (tmp_path / "tickets").mkdir()
    for name in ("a.txt", "b.txt"):
        (tmp_path / "tickets" / name).write_text("ticket text")
    return write(tmp_path)


def problems_of(path: Path) -> str:
    with pytest.raises(SpecError) as error:
        load(path)
    return error.value.message


def test_a_complete_file_loads_with_its_files_resolved(tmp_path: Path) -> None:
    loaded = load(project(tmp_path))
    (prompt,) = loaded.prompts
    assert prompt.project_name == f"support-bot{SEPARATOR}classify-ticket"
    assert prompt.system == "Classify the ticket as billing, shipping or technical."
    assert prompt.user is None
    assert prompt.golden == (tmp_path / "data" / "golden.csv").resolve()
    assert [p.name for p in prompt.inputs] == ["a.txt", "b.txt"]
    assert prompt.entry.params.given() == {"temperature": 0.0, "seed": 7, "stop": ["END"]}
    assert prompt.entry.task.output_format == "single_label"
    assert (prompt.entry.runs, prompt.entry.source.line if prompt.entry.source else None) == (3, 42)
    assert loaded.warnings == []


def test_prompt_text_can_live_in_files_and_is_normalised(tmp_path: Path) -> None:
    (tmp_path / "p").mkdir()
    (tmp_path / "p" / "sys.txt").write_bytes(b"\xef\xbb\xbf  Be brief.\r\nAnswer in one word.\r\n\r\n")
    text = """\
version: 1
project: x
prompts:
  - name: a
    system_file: p/sys.txt
    user: "Ticket: {{ ticket }}\\n"
    task: {type: summarization, goal: Summarize it}
    models: [m]
"""
    (prompt,) = load(write(tmp_path, text)).prompts
    assert prompt.system == "Be brief.\nAnswer in one word."
    assert prompt.user == "Ticket: {{ ticket }}"
    assert prompt.variables == ["ticket"]
    assert normalize_text("  a\r\nb \n") == "a\nb"


def test_a_typo_is_named_with_its_line_and_a_suggestion(tmp_path: Path) -> None:
    text = VALID.replace("    models: [gpt-4o-mini, claude-haiku]", "    modles: [gpt-4o-mini]")
    project(tmp_path)
    message = problems_of(write(tmp_path, text))
    assert "verano.yaml:18: prompts[classify-ticket].modles: is not a known setting. Did you mean 'models'?" in message
    assert "prompts[classify-ticket].models: is required" in message


def test_every_problem_is_reported_in_one_go_in_file_order(tmp_path: Path) -> None:
    text = """\
version: 1
project: x
prompts:
  - name: bad name!
    system: hi
    task: {type: poetry, goal: ok}
    models: []
    runs: 9
    params: {temperature: 5, seed: true, stop: [a, b, c, d, e]}
"""
    lines = problems_of(write(tmp_path, text)).splitlines()
    assert lines[0] == "verano.yaml has 8 problems:"
    expected = [
        "verano.yaml:4: prompts[bad name!].name: use letters, digits",
        "verano.yaml:6: prompts[bad name!].task.goal: must be at least 3 characters",
        "verano.yaml:6: prompts[bad name!].task.type: must be one of: classification, extraction",
        "verano.yaml:7: prompts[bad name!].models: needs at least 1 item(s)",
        "verano.yaml:8: prompts[bad name!].runs: must be at most 5",
        "verano.yaml:9: prompts[bad name!].params.seed: must be a number",
        "verano.yaml:9: prompts[bad name!].params.stop: at most 4 stop sequences",
        "verano.yaml:9: prompts[bad name!].params.temperature: must be at most 2",
    ]
    for got, want in zip(lines[1:], expected, strict=True):
        assert got.strip().startswith(want)


@pytest.mark.parametrize(
    ("change", "needle"),
    [
        ("version: 1", "version: 2"),
        ("version: 1", "version: 0"),
    ],
)
def test_only_version_one_is_read(tmp_path: Path, change: str, needle: str) -> None:
    message = problems_of(write(tmp_path, VALID.replace(change, needle)))
    assert "this CLI reads version 1" in message


def test_a_key_can_only_be_named_never_written(tmp_path: Path) -> None:
    message = problems_of(write(tmp_path, VALID.replace("env:OPENAI_API_KEY", "sk-live-1234567890")))
    assert "never write a key in this file" in message
    assert "sk-live" not in message
    assert "env:OPENAI_API_KEY" not in message or "for example" in message


@pytest.mark.parametrize(
    ("snippet", "needle"),
    [
        ("    system_file: p.txt\n", "give `system` or `system_file`, not both"),
        ("    user: hi\n    user_file: p.txt\n", "give `user` or `user_file`, not both"),
    ],
)
def test_the_prompt_is_given_one_way(tmp_path: Path, snippet: str, needle: str) -> None:
    text = VALID.replace("    params:", snippet + "    params:")
    assert needle in problems_of(write(tmp_path, text))


def test_a_prompt_must_exist_and_a_classification_needs_labels(tmp_path: Path) -> None:
    no_prompt = VALID.replace("    system: |\n      Classify the ticket as billing, shipping or technical.\n", "")
    assert "write a prompt" in problems_of(write(tmp_path, no_prompt))
    no_labels = VALID.replace("      allowed_outputs: [billing, shipping, technical]\n", "")
    assert "a classification task must list its allowed_outputs" in problems_of(write(tmp_path, no_labels))


def test_two_prompts_cannot_share_a_name_and_columns_need_a_golden_file(tmp_path: Path) -> None:
    entry = VALID.split("prompts:\n", 1)[1]
    doubled = VALID + entry
    assert "two prompts are called 'classify-ticket'" in problems_of(write(tmp_path, doubled))
    columns = VALID.replace("      golden: data/golden.csv\n", "      columns: {expected_output: x}\n")
    assert "`columns` describes the golden file" in problems_of(write(tmp_path, columns))


def test_a_yaml_mistake_says_where(tmp_path: Path) -> None:
    broken = problems_of(write(tmp_path, "version: 1\nproject: [oops\n"))
    assert "not valid YAML" in broken
    assert "verano.yaml:" in broken
    twice = problems_of(write(tmp_path, "version: 1\nproject: a\nproject: b\nprompts: []\n"))
    assert "'project' is written twice here" in twice
    assert "must start with settings" in problems_of(write(tmp_path, "- just\n- a list\n"))
    assert "must start with settings" in problems_of(write(tmp_path, ""))


def test_files_must_exist_and_stay_inside_the_folder(tmp_path: Path) -> None:
    secret = tmp_path.parent / "secret.txt"
    secret.write_text("private")
    try:
        text = (
            VALID.replace("data/golden.csv", "../secret.txt")
            .replace('"tickets/*.txt"', '"../*.txt", "nothing/*.txt"')
            .replace(
                "    system: |\n      Classify the ticket as billing, shipping or technical.\n",
                "    user_file: missing.txt\n",
            )
        )
        message = problems_of(write(tmp_path, text))
        assert "'../secret.txt' is outside this folder" in message
        assert "'../*.txt' reaches outside this folder" in message
        assert "'nothing/*.txt' matches no files" in message
        assert "'missing.txt' does not exist" in message
    finally:
        secret.unlink()


def test_a_link_cannot_lead_out_of_the_folder(tmp_path: Path) -> None:
    outside = tmp_path.parent / "elsewhere"
    outside.mkdir(exist_ok=True)
    (outside / "golden.csv").write_text("a,b\n1,2\n")
    (tmp_path / "data").mkdir()
    os.symlink(outside / "golden.csv", tmp_path / "data" / "golden.csv")
    assert "is outside this folder" in problems_of(write(tmp_path))


def test_the_golden_file_must_be_a_table_and_a_prompt_file_must_have_text(tmp_path: Path) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "golden.csv").write_text("a\n1\n")
    (tmp_path / "data" / "notes.md").write_text("hello")
    (tmp_path / "empty.txt").write_text("  \n")
    text = VALID.replace("data/golden.csv", "data/notes.md").replace(
        "    system: |\n      Classify the ticket as billing, shipping or technical.\n", "    system_file: empty.txt\n"
    )
    message = problems_of(write(tmp_path, text))
    assert "'notes.md' is not a table file" in message
    assert "'empty.txt' is empty" in message


def test_helpful_notes_for_thin_setups(tmp_path: Path) -> None:
    text = """\
version: 1
project: x
prompts:
  - name: a
    system: Summarize.
    task: {type: summarization, goal: Summarize the text}
    models: [m]
"""
    notes = load(write(tmp_path, text)).warnings
    assert any("no data" in n for n in notes)
    assert any("judge" in n for n in notes)


def test_finding_the_file(tmp_path: Path) -> None:
    with pytest.raises(CliError) as error:
        find_file(tmp_path)
    assert error.value.hint is not None
    assert "verano init" in error.value.hint
    write(tmp_path)
    assert find_file(tmp_path) == tmp_path / "verano.yaml"
    with pytest.raises(CliError, match="does not exist"):
        load(tmp_path / "nope.yaml")
