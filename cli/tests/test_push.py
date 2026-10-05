"""`verano push` against an in-memory Verano: first push, repeat push, changes, dry runs and mistakes."""

from pathlib import Path

import pytest

from tests.conftest import Run
from tests.platform import FakePlatform

SECRET = "sk-test-SECRET-9876"

FILE = """\
version: 1
project: shop
keys:
  openai: env:OPENAI_API_KEY
prompts:
  - name: tag
    source: {{file: app/tag.py, line: 12}}
    system: |
      Tag the item.
    params: {{temperature: 0}}
    task: {{type: classification, goal: Tag items, allowed_outputs: [a, b]}}
    models: {models}
"""


def setup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, models: str = "[gpt-4o-mini, gpt-4o]", text: str = ""
) -> Path:
    monkeypatch.setenv("OPENAI_API_KEY", SECRET)
    path = tmp_path / "verano.yaml"
    path.write_text(text or FILE.format(models=models))
    return path


def test_the_first_push_sets_up_the_project_the_key_the_models_and_the_prompt(
    platform: FakePlatform, run: Run, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup(tmp_path, monkeypatch)
    result = run("push")
    assert result.code == 0
    for line in (
        "project created",
        "openai: key added (ends …9876), 2 models found",
        "models selected: gpt-4o-mini, gpt-4o",
        "prompt created (version 1)",
        "Pushed 1 prompt.",
    ):
        assert line in result.err
    (project,) = platform.projects
    assert project["name"] == "shop · tag"
    assert [p["is_selected"] for p in platform.profiles[project["id"]]] == [True, True]
    (prompt,) = platform.prompts[project["id"]]
    assert prompt["latest_version"]["system_template"] == "Tag the item."
    assert prompt["latest_version"]["default_params"] == {"temperature": 0.0}
    assert prompt["latest_version"]["change_reason"] == "verano push from app/tag.py:12"


def test_the_key_is_sent_only_to_the_server_and_never_shown_or_saved(
    platform: FakePlatform, run: Run, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup(tmp_path, monkeypatch)
    result = run("push")
    assert platform.secrets == [SECRET]
    assert SECRET not in result.out + result.err
    assert not any(SECRET in p.read_text(errors="ignore") for p in tmp_path.rglob("*") if p.is_file())


def test_pushing_again_changes_nothing(
    platform: FakePlatform, run: Run, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup(tmp_path, monkeypatch)
    run("push")
    platform.calls.clear()
    again = run("push")
    assert again.code == 0
    for line in (
        "project exists",
        "openai: key already set",
        "models already selected",
        "prompt unchanged (version 1)",
    ):
        assert line in again.err
    assert platform.writes == []
    assert len(platform.projects) == 1
    assert len(platform.secrets) == 1


def test_only_a_real_change_to_the_prompt_makes_a_new_version_and_names_where_it_changed(
    platform: FakePlatform, run: Run, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = setup(tmp_path, monkeypatch)
    run("push")
    path.write_bytes(path.read_bytes().replace(b"Tag the item.\n", b"Tag the item.\r\n\r\n"))
    assert "prompt unchanged (version 1)" in run("push").err
    path.write_text(path.read_text().replace("Tag the item.", "Tag the item with one letter."))
    changed = run("push")
    assert "prompt changed from app/tag.py:12: saved version 2" in changed.err
    path.write_text(path.read_text().replace("temperature: 0}", "temperature: 0.3}"))
    assert "saved version 3" in run("push").err
    (prompt,) = platform.prompts[platform.projects[0]["id"]]
    assert prompt["latest_version"]["version"] == 3
    assert "saved version" not in run("push").err


def test_a_dry_run_reports_what_would_happen_and_writes_nothing(
    platform: FakePlatform, run: Run, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = setup(tmp_path, monkeypatch)
    fresh = run("push", "--dry-run")
    assert fresh.code == 0
    for line in (
        "would: create the project",
        "would: add the openai key from env:OPENAI_API_KEY",
        "would: create the prompt (version 1)",
    ):
        assert line in fresh.err
    assert "Dry run finished; nothing was changed." in fresh.err
    assert platform.writes == []
    assert platform.projects == []
    run("push")
    path.write_text(path.read_text().replace("Tag the item.", "Tag it."))
    platform.calls.clear()
    later = run("push", "--dry-run")
    assert "would: save a new prompt version from app/tag.py:12 (now version 1)" in later.err
    assert platform.writes == []


def test_a_missing_key_variable_stops_everything_before_any_change(
    platform: FakePlatform, run: Run, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup(tmp_path, monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "  ")
    result = run("push")
    assert result.code == 1
    assert "OPENAI_API_KEY (the openai key) is not set or is empty" in result.err
    assert platform.projects == []


def test_a_provider_verano_does_not_know_is_listed_and_a_rejected_key_is_reported(
    platform: FakePlatform, run: Run, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = setup(tmp_path, monkeypatch)
    path.write_text(path.read_text().replace("  openai: env:OPENAI_API_KEY", "  openia: env:OPENAI_API_KEY"))
    unknown = run("push")
    assert unknown.code == 1
    assert "doesn't know a provider called 'openia'" in unknown.err
    assert "anthropic, groq, ollama, openai" in unknown.err
    path.write_text(path.read_text().replace("openia", "openai"))
    monkeypatch.setenv("OPENAI_API_KEY", "rejected-key")
    rejected = run("push")
    assert rejected.code == 1
    assert "key was rejected" in rejected.err
    assert "rejected-key" not in rejected.err


def test_a_key_is_optional_for_providers_that_need_none(
    platform: FakePlatform, run: Run, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = setup(tmp_path, monkeypatch, models="[llama3]")
    path.write_text(path.read_text().replace("  openai: env:OPENAI_API_KEY", "  ollama: none"))
    result = run("push")
    assert result.code == 0
    assert "ollama: key added, 1 models found" in result.err
    assert platform.secrets == []


def test_model_names_are_resolved_loosely_but_never_guessed(
    platform: FakePlatform, run: Run, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = setup(tmp_path, monkeypatch, models="[GPT-4O-MINI]")
    assert "models selected: gpt-4o-mini" in run("push").err
    path.write_text(path.read_text().replace("GPT-4O-MINI", "gpt-5-nano"))
    unknown = run("push")
    assert unknown.code == 1
    assert "No model called 'gpt-5-nano'" in unknown.err
    assert "Available: gpt-4o, gpt-4o-mini" in unknown.err
    path.write_text(
        path.read_text()
        .replace("gpt-5-nano", "gpt-4o-mini")
        .replace("  openai:", "  groq: env:OPENAI_API_KEY\n  openai:")
    )
    ambiguous = run("push")
    assert ambiguous.code == 1
    assert "available from more than one key: groq/gpt-4o-mini, openai/gpt-4o-mini" in ambiguous.err
    path.write_text(path.read_text().replace("[gpt-4o-mini]", "[groq/gpt-4o-mini]"))
    assert run("push").code == 0


def test_the_judge_must_exist_and_models_no_longer_listed_are_unselected(
    platform: FakePlatform, run: Run, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = setup(tmp_path, monkeypatch)
    run("push")
    path.write_text(path.read_text().replace("[gpt-4o-mini, gpt-4o]", "[gpt-4o]"))
    assert "models selected: gpt-4o" in run("push").err
    selected = {p["model_name"] for p in platform.profiles[platform.projects[0]["id"]] if p["is_selected"]}
    assert selected == {"gpt-4o"}
    path.write_text(path.read_text().replace("    models: [gpt-4o]", "    models: [gpt-4o]\n    judge: nobody"))
    result = run("push")
    assert result.code == 1
    assert "No model called 'nobody'" in result.err


def test_one_prompt_failing_does_not_stop_the_others_and_the_exit_code_says_so(
    platform: FakePlatform, run: Run, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = setup(tmp_path, monkeypatch)
    second = (
        path.read_text()
        .split("prompts:\n", 1)[1]
        .replace("name: tag", "name: broken")
        .replace("[gpt-4o-mini, gpt-4o]", "[nope]")
    )
    path.write_text(path.read_text() + second)
    result = run("push")
    assert result.code == 1
    assert "1 of 2 prompts could not be pushed: broken." in result.err
    assert {p["name"] for p in platform.projects} == {"shop · tag", "shop · broken"}
    assert platform.prompts[platform.projects[0]["id"]]
    only = run("push", "tag")
    assert only.code == 0
    assert "broken" not in only.err
    missing = run("push", "nothing")
    assert missing.code == 1
    assert "has no prompt called 'nothing'" in missing.err


def test_projects_are_found_on_later_pages_and_duplicate_names_are_refused(
    platform: FakePlatform, run: Run, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup(tmp_path, monkeypatch)
    wanted = platform.add_project("shop · tag")
    for number in range(5):
        platform.add_project(f"other {number}")
    result = run("push")
    assert result.code == 0
    assert "project exists" in result.err
    assert len(platform.projects) == 6
    assert platform.credentials[wanted["id"]]
    platform.add_project("shop · tag")
    duplicate = run("push")
    assert duplicate.code == 1
    assert '2 projects are called "shop · tag"' in duplicate.err


def test_push_needs_a_sign_in_and_a_valid_file(
    platform: FakePlatform, run: Run, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup(tmp_path, monkeypatch)
    monkeypatch.delenv("VERANO_API_TOKEN")
    unsigned = run("push")
    assert unsigned.code == 1
    assert "not signed in" in unsigned.err
    assert platform.calls == []
    monkeypatch.setenv("VERANO_API_TOKEN", "vrn_ci")
    (tmp_path / "verano.yaml").write_text("version: 1\n")
    invalid = run("push")
    assert invalid.code == 1
    assert "has 2 problems" in invalid.err
    assert platform.calls == []
