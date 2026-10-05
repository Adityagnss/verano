"""`verano run` and `verano status`: cost first, progress, results, the quality gate and the ways it can end."""

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import click
import pytest

from tests.conftest import Run
from tests.platform import FakePlatform
from verano import data, runner
from verano.client import ApiClient
from verano.loader import load

TICKETS = "ticket,expected\nCard charged twice,billing\nWhere is my parcel,shipping\nApp crashes,technical\n"
YAML = """\
version: 1
project: shop
keys:
  openai: env:OPENAI_API_KEY
  anthropic: env:ANTHROPIC_API_KEY
prompts:
  - name: tag
    system: Tag the ticket.
    task: {type: classification, goal: Tag tickets by team, allowed_outputs: [billing, shipping, technical]}
    data:
      cases: {file: tickets.csv, input: ticket, expected: expected}
    models: [gpt-4o-mini, claude-haiku]
"""


@pytest.fixture(autouse=True)
def _fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(data, "POLL_S", 0)
    monkeypatch.setattr(data, "WAIT_S", 0.05)
    monkeypatch.setattr(runner, "POLL_S", 0)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-1234")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-5678")


def pushed(platform: FakePlatform, run: Run, tmp_path: Path, extra: str = "", text: str = YAML) -> Path:
    (tmp_path / "tickets.csv").write_text(TICKETS)
    path = tmp_path / "verano.yaml"
    path.write_text(text + extra)
    result = run("push")
    assert result.code == 0, result.err
    return path


def test_a_run_shows_the_cost_first_then_progress_results_and_a_link(
    platform: FakePlatform, run: Run, tmp_path: Path
) -> None:
    pushed(platform, run, tmp_path)
    result = run("run", "--yes")
    assert result.code == 0, result.err
    pid = platform.projects[0]["id"]
    for line in (
        "6 model calls on 3 test cases.",
        "Estimated cost: $0.04",
        "Started. Watch it live: http://verano.test/projects/",
        "calls · $0.02 so far",
        "Model         Quality  Passed",
        "gpt-4o-mini   90%      90%",
        "claude-haiku  90%",
        f"Results: http://verano.test/projects/{pid}/results?experiment=",
    ):
        assert line in result.err, line
    assert result.out == ""


def test_the_same_defaults_as_the_web_app_apply_only_where_a_model_accepts_them(
    platform: FakePlatform, run: Run, tmp_path: Path
) -> None:
    path = pushed(platform, run, tmp_path)
    run("run", "--yes")
    openai, claude = platform.started[0]["models"]
    assert openai["params"] == {"temperature": 0, "seed": 42}
    assert claude["params"] == {"temperature": 0}
    path.write_text(path.read_text().replace("    models:", "    params: {temperature: 0.3}\n    runs: 3\n    models:"))
    run("push", "--no-data")
    run("run", "--yes")
    openai, claude = platform.started[1]["models"]
    assert openai["params"] == {"temperature": 0.3, "seed": 42}
    assert (openai["runs"], claude["runs"]) == (3, 3)


def test_without_a_person_to_ask_it_does_not_start_unless_told_to(
    platform: FakePlatform, run: Run, tmp_path: Path
) -> None:
    pushed(platform, run, tmp_path)
    result = run("run")
    assert result.code == 1
    assert "Estimated cost: $0.04" in result.err
    assert "Not starting without your confirmation" in result.err
    assert platform.started == []
    assert run("run", "--ci").code == 0
    assert len(platform.started) == 1


def test_max_cost_stops_a_run_that_would_cost_more_and_a_cap_is_passed_on(
    platform: FakePlatform, run: Run, tmp_path: Path
) -> None:
    path = pushed(platform, run, tmp_path)
    over = run("run", "--yes", "--max-cost", "0.01")
    assert over.code == 1
    assert "over --max-cost $0.01. Nothing was started." in over.err
    platform.price = None
    unknown = run("run", "--yes", "--max-cost", "5")
    assert "price of some models is unknown" in unknown.err
    assert platform.started == []
    path.write_text(path.read_text().replace("    models:", "    budget: 0.02\n    models:"))
    platform.price = "0.0420"
    run("push", "--no-data")
    run("run", "--yes")
    assert platform.started[0]["budget_cap"] == "0.02"


def test_asking_and_declining_stops_before_anything_is_sent(
    platform: FakePlatform, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, run: Run
) -> None:
    path = pushed(platform, run, tmp_path)
    loaded = load(path)
    answers = iter([False, True])
    monkeypatch.setattr("typer.confirm", lambda *a, **k: next(answers))
    api = ApiClient("http://verano.test", "vrn_ci")
    runner_ = runner.Runner(api, loaded, "http://verano.test", interactive=True, sleep=lambda s: None)
    with pytest.raises(click.exceptions.Abort):
        runner_.run(None)
    assert platform.started == []
    (accepted,) = runner_.run(None)
    assert accepted.error is None
    assert len(platform.started) == 1


def test_a_gate_fails_the_pipeline_only_with_ci_and_names_what_missed(
    platform: FakePlatform, run: Run, tmp_path: Path
) -> None:
    pushed(platform, run, tmp_path, "    gate: {min_quality: 0.85, min_pass_rate: 0.95}\n")
    platform.quality = {"claude-haiku": 0.7}
    plain = run("run", "--yes")
    assert plain.code == 0
    assert "claude-haiku: quality 70% is below the minimum 85%." in plain.err
    assert "(This would fail the gate under `verano run --ci`.)" in plain.err
    gated = run("run", "--ci")
    assert gated.code == 2
    assert "claude-haiku: 70% passed, below the minimum 95%." in gated.err
    assert "The quality gate failed for: tag." in gated.err
    platform.quality = {"gpt-4o-mini": 0.97, "claude-haiku": 0.97}
    ok = run("run", "--ci")
    assert ok.code == 0
    assert "Quality gate passed." in ok.err
    assert "gpt-4o-mini: quality" not in ok.err


def test_a_drop_is_measured_against_the_last_run_of_the_same_models_and_settings(
    platform: FakePlatform, run: Run, tmp_path: Path
) -> None:
    path = pushed(platform, run, tmp_path, "    gate: {max_drop: 0.05}\n")
    first = run("run", "--ci")
    assert first.code == 0
    assert "no earlier run to compare with, so the drop was not checked" in first.err
    platform.quality = {"gpt-4o-mini": 0.8}
    dropped = run("run", "--ci")
    assert dropped.code == 2
    assert "gpt-4o-mini: quality fell 10 points (90% → 80%); at most 5 allowed." in dropped.err
    platform.quality = {"gpt-4o-mini": 0.87}
    assert run("run", "--ci").code == 0
    path.write_text(path.read_text().replace("    models:", "    runs: 2\n    models:"))
    run("push", "--no-data")
    platform.quality = {"gpt-4o-mini": 0.3}
    other_settings = run("run", "--ci")
    assert other_settings.code == 0
    assert "no earlier run to compare with" in other_settings.err


def test_a_run_that_stopped_early_fails_the_gate_and_says_why(platform: FakePlatform, run: Run, tmp_path: Path) -> None:
    pushed(platform, run, tmp_path, "    gate: {min_quality: 0.1}\n    budget: 0.001\n")
    platform.stop_reason = "Budget cap reached ($0.001)."
    result = run("run", "--ci")
    assert result.code == 2
    assert "The run stopped early (Budget cap reached ($0.001)), so its scores can't be trusted." in result.err


def test_json_output_is_one_document_on_standard_output(platform: FakePlatform, run: Run, tmp_path: Path) -> None:
    pushed(platform, run, tmp_path, "    gate: {min_quality: 0.95}\n")
    result = run("run", "--ci", "--json")
    assert result.code == 2
    report: dict[str, Any] = json.loads(result.out)
    assert report["passed"] is False
    (entry,) = report["prompts"]
    assert entry["name"] == "tag"
    assert entry["gate"]["passed"] is False
    assert entry["gate"]["failures"][0].startswith("gpt-4o-mini: quality 90%")
    assert entry["link"].startswith("http://verano.test/projects/")
    assert {m["model"] for m in entry["models"]} == {"gpt-4o-mini", "claude-haiku"}


def test_things_that_are_not_ready_are_named_before_anything_is_sent(
    platform: FakePlatform, run: Run, tmp_path: Path
) -> None:
    (tmp_path / "tickets.csv").write_text(TICKETS)
    (tmp_path / "verano.yaml").write_text(YAML)
    missing = run("run", "--yes")
    assert missing.code == 1
    assert 'There is no project "shop · tag" yet.' in missing.err
    assert "verano push" in missing.err
    run("push", "--no-data")
    no_cases = run("run", "--yes")
    assert "This project has no test cases." in no_cases.err
    pid = platform.projects[0]["id"]
    platform.draft(pid)["item_count"] = 3
    unapproved = run("run", "--yes")
    assert "are not approved yet" in unapproved.err
    assert platform.started == []


def test_one_prompt_failing_does_not_stop_the_others(platform: FakePlatform, run: Run, tmp_path: Path) -> None:
    second = (
        YAML.split("prompts:\n", 1)[1]
        .replace("name: tag", "name: other")
        .replace("[gpt-4o-mini, claude-haiku]", "[gpt-4o-mini]")
    )
    path = pushed(platform, run, tmp_path)
    path.write_text(path.read_text() + second)
    run("push")
    path.write_text(path.read_text().replace("[gpt-4o-mini]", "[nope]"))
    result = run("run", "--yes")
    assert result.code == 1
    assert "1 of 2 prompts could not be run: other." in result.err
    assert len(platform.started) == 1
    only = run("run", "tag", "--yes")
    assert only.code == 0
    assert run("run", "nothing", "--yes").code == 1


def test_a_run_that_never_finishes_is_stopped_and_scoring_that_fails_is_reported(
    platform: FakePlatform, run: Run, tmp_path: Path
) -> None:
    path = pushed(platform, run, tmp_path)
    loaded = load(path)
    api = ApiClient("http://verano.test", "vrn_ci")
    clock = iter(range(0, 10_000, 100)).__next__
    platform.stall = True
    slow = runner.Runner(
        api, loaded, "http://verano.test", yes=True, timeout_s=300, sleep=lambda s: None, clock=lambda: clock()
    )
    (result,) = slow.run(None)
    assert result.error is not None
    assert "did not finish within 300 seconds" in result.error
    assert platform.experiments[platform.projects[0]["id"]][-1]["status"] == "cancelled"
    platform.stall = False
    platform.scoring_failed = True
    (failed,) = runner.Runner(api, loaded, "http://verano.test", yes=True, sleep=lambda s: None).run(None)
    assert failed.error is not None
    assert "Scoring the answers failed" in failed.error


def test_pressing_ctrl_c_stops_the_experiment_so_it_stops_spending(
    platform: FakePlatform, run: Run, tmp_path: Path
) -> None:
    path = pushed(platform, run, tmp_path)
    api = ApiClient("http://verano.test", "vrn_ci")
    platform.stall = True

    def interrupt(seconds: float) -> None:
        raise KeyboardInterrupt

    runner_ = runner.Runner(api, load(path), "http://verano.test", yes=True, sleep=interrupt)
    with pytest.raises(KeyboardInterrupt):
        runner_.run(None)
    assert platform.experiments[platform.projects[0]["id"]][-1]["status"] == "cancelled"


def test_status_shows_the_latest_finished_run_or_says_there_is_none(
    platform: FakePlatform, run: Run, tmp_path: Path
) -> None:
    (tmp_path / "tickets.csv").write_text(TICKETS)
    (tmp_path / "verano.yaml").write_text(YAML)
    assert "There is no project" in run("status").out
    pushed(platform, run, tmp_path)
    assert "No finished run yet. Start one with `verano run`." in run("status").out
    run("run", "--yes")
    shown = run("status")
    assert shown.code == 0
    assert "Latest run: 2026-10-05 12:30 · configuration " in shown.out
    assert "gpt-4o-mini   90%" in shown.out
    assert "/results?experiment=" in shown.out
    assert Decimal("0") == Decimal(0)
