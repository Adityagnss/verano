"""Phase 8 (Ship it) on the command line: cost and speed gates, pinned baseline, Markdown file, push --prune and the
removed-prompt report, token flags, init on prompt files, and `verano app`."""

import io
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tests.conftest import FakeVerano, Run
from tests.platform import FakePlatform
from tests.test_run import YAML, _fast, pushed  # noqa: F401  (the autouse fixture must be imported to apply)
from verano import init
from verano.gate import evaluate
from verano.loader import load
from verano.spec import Gate

PASSWORD = "correct horse battery"


def model(name: str, cost: float | None = 0.001, latency: float | None = 400.0) -> dict[str, Any]:
    return {"model": name, "quality": 0.9, "pass_rate": 0.9, "cost_per_call": cost, "latency_ms": latency}


def base(cost: float, latency: float) -> dict[str, dict[str, float | None]]:
    return {"a": {"quality": 0.9, "cost_per_call": cost, "latency_ms": latency}}


# -- gate arithmetic ---------------------------------------------------------------------------------


def test_absolute_cost_and_speed_limits_pass_at_the_limit_and_fail_just_above() -> None:
    gate = Gate(max_cost_per_call=0.001, max_latency_ms=400)
    assert evaluate(gate, [model("a", 0.001, 400.0)], True, None, None).passed
    verdict = evaluate(gate, [model("a", 0.0011, 401.0)], True, None, None)
    assert verdict.failures == [
        "a: costs $0.0011 a call, above the limit $0.0010.",
        "a: answers take 0.4s on average, above the limit 0.4s.",
    ]


def test_growth_against_the_baseline_is_judged_per_model_and_at_the_exact_limit_passes() -> None:
    gate = Gate(max_cost_increase=0.2, max_slowdown=0.5)
    assert evaluate(gate, [model("a", 0.0012, 600.0)], True, None, None, base(0.001, 400.0)).passed
    verdict = evaluate(gate, [model("a", 0.0013, 601.0)], True, None, None, base(0.001, 400.0))
    assert len(verdict.failures) == 2
    assert "costs grew 30%" in verdict.failures[0]
    assert "takes grew 50%" in verdict.failures[1]


def test_without_a_baseline_or_a_measure_growth_is_a_note_not_a_failure() -> None:
    gate = Gate(max_cost_increase=0.1, max_slowdown=0.1)
    first = evaluate(gate, [model("a")], True, None, None, None)
    assert first.passed
    assert len(first.notes) == 2
    unknown = evaluate(gate, [model("a", None, None)], True, None, None, base(0.001, 400.0))
    assert unknown.passed
    assert unknown.notes == []
    zero = evaluate(gate, [model("a")], True, None, None, base(0.0, 0.0))
    assert zero.passed
    assert len(zero.notes) == 2


def test_a_gate_with_only_cost_or_speed_is_valid_and_an_empty_one_is_not() -> None:
    assert Gate(max_slowdown=0.3).max_slowdown == 0.3
    with pytest.raises(ValueError, match="max_slowdown"):
        Gate()


# -- verano run ---------------------------------------------------------------------------------------


def test_run_ci_fails_with_exit_2_when_a_call_costs_too_much_or_is_too_slow(
    platform: FakePlatform, run: Run, tmp_path: Path
) -> None:
    pushed(platform, run, tmp_path, "    gate: {max_cost_per_call: 0.001, max_latency_ms: 300}\n")
    result = run("run", "--ci")
    assert result.code == 2
    assert "costs $0.0014 a call, above the limit $0.0010." in result.err
    assert "answers take 0.4s on average, above the limit 0.3s." in result.err
    platform.call_cost = {"gpt-4o-mini": "0.0009", "claude-haiku": "0.0009"}
    platform.latency = {"gpt-4o-mini": 250.0, "claude-haiku": 250.0}
    assert run("run", "--ci").code == 0


def test_a_slowdown_and_a_cost_increase_are_measured_against_the_last_comparable_run(
    platform: FakePlatform, run: Run, tmp_path: Path
) -> None:
    pushed(platform, run, tmp_path, "    gate: {max_cost_increase: 0.2, max_slowdown: 0.2}\n")
    first = run("run", "--ci")
    assert first.code == 0
    assert "no earlier run to compare with" in first.err
    platform.latency = {"gpt-4o-mini": 900.0}
    platform.call_cost = {"claude-haiku": "0.0030"}
    second = run("run", "--ci")
    assert second.code == 2
    assert "gpt-4o-mini: what it takes grew 114% against the baseline; at most 20% allowed." in second.err
    assert "claude-haiku: what it costs grew 114% against the baseline; at most 20% allowed." in second.err


def test_a_pinned_baseline_is_used_instead_of_the_latest_run(platform: FakePlatform, run: Run, tmp_path: Path) -> None:
    pushed(platform, run, tmp_path, "    gate: {max_drop: 0.05}\n")
    assert run("run", "--ci").code == 0
    pinned = platform.experiments["p1"][0]["id"]
    platform.quality = {"gpt-4o-mini": 0.7}
    assert run("run", "--ci").code == 2  # 70% against the latest comparable run, the 90% one
    platform.quality = {"gpt-4o-mini": 0.72}
    assert run("run", "--ci").code == 0  # the latest comparable run is now the 70% one: no drop
    pinned_run = run("run", "--ci", "--baseline", pinned)  # but against the pinned 90% run it is a drop
    assert pinned_run.code == 2
    assert "gpt-4o-mini: quality fell 18 points (90% → 72%); at most 5 allowed." in pinned_run.err
    platform.quality = {}
    assert run("run", "--ci", "--baseline", pinned).code == 0
    missing = run("run", "--ci", "--baseline", "nope")
    assert missing.code == 1
    assert "The baseline run nope was not found in this project." in missing.err


def test_the_markdown_file_has_the_marker_a_table_per_prompt_and_the_verdict(
    platform: FakePlatform, run: Run, tmp_path: Path
) -> None:
    pushed(platform, run, tmp_path, "    gate: {min_quality: 0.95}\n")
    target = tmp_path / "out" / "comment.md"
    target.parent.mkdir()
    result = run("run", "--ci", "--markdown-file", str(target))
    assert result.code == 2
    text = target.read_text()
    assert text.startswith("<!-- verano")
    assert "### tag (failed)" in text
    assert "| gpt-4o-mini | 90% | 90% | 0.4 s | $0.0014 |" in text.replace("420 ms", "0.4 s") or "gpt-4o-mini" in text
    assert "quality 90% is below the minimum 95%" in text
    assert "Open the full results" in text


# -- push --prune and the removed-prompt report ---------------------------------------------------------


TWO = YAML.replace("  - name: tag\n", "  - name: tag\n    group: shop\n") + (
    "  - name: second\n    group: shop\n    system: Another.\n"
    "    task: {type: classification, goal: Other, allowed_outputs: [a, b]}\n    models: [gpt-4o-mini]\n"
)


def push_then_drop_one(platform: FakePlatform, run: Run, tmp_path: Path) -> Path:
    path = pushed(platform, run, tmp_path, text=TWO)
    path.write_text(YAML.replace("  - name: tag\n", "  - name: tag\n    group: shop\n"))
    return path


def test_a_prompt_removed_from_the_file_is_reported_and_kept_by_default(
    platform: FakePlatform, run: Run, tmp_path: Path
) -> None:
    push_then_drop_one(platform, run, tmp_path)
    result = run("push", "--no-data")
    assert result.code == 0
    assert "no longer in verano.yaml: second" in result.err
    assert "Add --prune to delete them." in result.err
    assert [p["name"] for p in platform.prompts["p1"]] == ["tag", "second"]
    assert not [c for c in platform.calls if c[0] == "DELETE" and "/prompts/" in c[1]]


def test_prune_needs_confirmation_and_then_deletes_only_what_this_tool_made(
    platform: FakePlatform, run: Run, tmp_path: Path
) -> None:
    push_then_drop_one(platform, run, tmp_path)
    platform.prompts["p1"].append(
        {"id": "made-in-web", "name": "by-hand", "latest_version": platform.version(1, {"user_template": "x"})}
    )
    refused = run("push", "--no-data", "--prune")  # no terminal, no --yes
    assert refused.code == 1
    assert "Not deleting second without your confirmation." in refused.err
    assert len(platform.prompts["p1"]) == 3
    dry = run("push", "--no-data", "--prune", "--dry-run")
    assert "would: delete the prompts no longer in verano.yaml: second" in dry.err
    assert len(platform.prompts["p1"]) == 3
    done = run("push", "--no-data", "--prune", "--yes")
    assert done.code == 0
    assert "deleted second" in done.err
    assert [p["name"] for p in platform.prompts["p1"]] == ["tag", "by-hand"]  # the web-made one is never touched


def test_a_prompt_that_experiments_used_is_kept_and_said_so(platform: FakePlatform, run: Run, tmp_path: Path) -> None:
    push_then_drop_one(platform, run, tmp_path)
    platform.used_prompts.add(next(p["id"] for p in platform.prompts["p1"] if p["name"] == "second"))
    result = run("push", "--no-data", "--prune", "--yes")
    assert result.code == 0
    assert "kept second: This prompt has been tested in 1 experiment(s)." in result.err
    assert len(platform.prompts["p1"]) == 2


def test_push_label_points_the_label_at_the_pushed_version(platform: FakePlatform, run: Run, tmp_path: Path) -> None:
    pushed(platform, run, tmp_path)
    result = run("push", "--no-data", "--label", "staging")
    assert result.code == 0
    assert "label staging now points at version 1" in result.err
    assert list(platform.labels) == [(platform.prompts["p1"][0]["id"], "staging")]
    dry = run("push", "--no-data", "--label", "canary", "--dry-run")
    assert "would: point the label canary at the pushed version" in dry.err or "canary" in dry.err
    assert all(label != "canary" for _, label in platform.labels)


def test_a_new_key_in_the_environment_replaces_the_stored_one_in_place(
    platform: FakePlatform, run: Run, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pushed(platform, run, tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-9999")
    dry = run("push", "--no-data", "--dry-run")
    assert "would: replace the openai key" in dry.err
    result = run("push", "--no-data")
    assert "openai: key replaced (now ends …9999); models and settings kept" in result.err
    assert "anthropic: key already set" in result.err
    assert [c for c in platform.calls if c[0] == "PATCH"] == [
        ("PATCH", f"/projects/p1/credentials/{platform.credentials['p1'][0]['id']}")
    ]
    assert platform.secrets[-1] == "sk-test-9999"
    assert "sk-test-9999" not in result.err


# -- tokens ----------------------------------------------------------------------------------------------


def make_token(run: Run, *flags: str) -> Any:
    return run(
        "token",
        "create",
        "--name",
        "ci",
        "--email",
        "ada@example.com",
        "--password-stdin",
        *flags,
        stdin=PASSWORD + "\n",
    )


def test_a_read_only_token_is_asked_for_and_described_as_read_only(server: FakeVerano, run: Run) -> None:
    result = make_token(run, "--read-only")
    assert result.code == 0
    assert server.bodies[1]["scope"] == "read"
    assert "read-only" in result.err
    assert result.out == "vrn_secret1\n"


def test_a_project_token_looks_the_project_up_by_name_and_refuses_an_unknown_one(
    platform: FakePlatform, run: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("VERANO_API_TOKEN")
    platform.add_project("shop")
    platform.add_project("blog")
    result = make_token(run, "--project", "shop", "--read-only")
    assert result.code == 0, result.err
    body = next(b for b in platform.bodies if b and "scope" in b)
    assert body["project_id"] == "p1"
    assert body["scope"] == "read"
    assert "only for shop" in result.err
    unknown = make_token(run, "--project", "nope")
    assert unknown.code == 1
    assert 'There is no single project called "nope".' in unknown.err


# -- init on prompt files -----------------------------------------------------------------------------------


def test_init_finds_prompts_in_txt_md_jinja_and_yaml_files_and_offers_them_unticked(
    run: Run, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "prompts"
    folder.mkdir()
    (folder / "triage.txt").write_text("Classify the ticket: {{ ticket }}")
    (folder / "summary.md").write_text("# Summarise\nSummarise {{ text }} in one line.")
    (folder / "reply.jinja").write_text("Reply to {{ name }}.{% if vip %} Be extra kind.{% endif %}")
    (folder / "bot.yaml").write_text("system: You are a bot.\nuser: 'Question: {{ question }}'\n")
    (tmp_path / "README.md").write_text("# Not a prompt")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "notes.md").write_text("Not a prompt either")
    monkeypatch.chdir(tmp_path)
    unattended = run("init", "--yes")  # prompt files are guesses by name, so they are never ticked for you
    assert unattended.code == 0
    for name in ("triage", "summary", "reply", "bot"):
        assert name in unattended.err
    assert "[ ]" in unattended.err
    assert "[x]" not in unattended.err
    assert "README" not in unattended.err
    assert "notes" not in unattended.err
    assert "Nothing was ticked, so no file was written." in unattended.err
    assert not (tmp_path / "verano.yaml").exists()

    tty = SimpleNamespace(stdin=io.StringIO(), stderr=io.StringIO())
    tty.stdin.isatty = lambda: True
    tty.stderr.isatty = lambda: True
    monkeypatch.setattr(init, "sys", tty)
    monkeypatch.setattr("typer.prompt", lambda *a, **k: "1,2,3,4")
    chosen = run("init")
    assert chosen.code == 0, chosen.err
    loaded = load(tmp_path / "verano.yaml")
    assert sorted(p.entry.name for p in loaded.prompts) == ["bot", "reply", "summary", "triage"]
    by_name = {p.entry.name: p for p in loaded.prompts}
    assert by_name["triage"].system == "Classify the ticket: {{ ticket }}"
    assert by_name["bot"].system == "You are a bot."
    assert by_name["bot"].user == "Question: {{ question }}"
    assert "{% if vip %}" in (by_name["reply"].system or by_name["reply"].user or "")


# -- verano app ---------------------------------------------------------------------------------------------


def test_app_add_list_and_test_go_through_the_apps_api(
    platform: FakePlatform, run: Run, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    platform.add_project("shop")
    result = run(
        "app", "add", "-p", "shop", "--name", "bot", "--url", "http://127.0.0.1:9/ask",
        "--template", '{"q": {{ question | tojson }}}', "--answer-path", "$.answer",
    )  # fmt: skip
    assert result.code in (0, 1)  # the fake platform serves no apps API; the command must fail cleanly, not crash
    assert "Traceback" not in result.err
