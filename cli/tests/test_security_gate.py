"""`verano run --security`: the approved pack is run with the prompt's models and judge, the server's gate decides, and
with `--ci` a failing category exits with 2 and is named."""

from pathlib import Path
from typing import Any

from tests.conftest import Run
from tests.platform import FakePlatform
from tests.test_run import _fast, pushed  # noqa: F401  (the autouse fixture must be imported to apply)

JUDGED = "    judge: gpt-4o-mini\n"
PACK = {"id": "pack1", "status": "approved", "name": "Security pack"}


def category(name: str, rate: float, earlier: float | None = None) -> dict[str, Any]:
    return {
        "category": name,
        "title": name.replace("_", " ").title(),
        "owasp": "LLM01",
        "answers": 10,
        "resisted": round(rate * 10),
        "pass_rate": rate,
        "earlier_pass_rate": earlier,
        "failing_examples": [],
    }


def gate(passed: bool, categories: list[dict[str, Any]], failures: list[str]) -> dict[str, Any]:
    return {"passed": passed, "categories": categories, "failures": [{"category": "x", "message": m} for m in failures]}


def with_pack(platform: FakePlatform, **security_gate: Any) -> None:
    platform.security_packs["p1"] = [PACK]
    platform.security_gate = security_gate


def test_a_passing_pack_prints_each_category_and_exits_clean(platform: FakePlatform, run: Run, tmp_path: Path) -> None:
    pushed(platform, run, tmp_path, JUDGED)
    with_pack(platform, **gate(True, [category("jailbreak", 0.9), category("system_prompt_leak", 1.0, 0.95)], []))
    result = run("run", "--security", "--ci")
    assert result.code == 0, result.err
    assert "Jailbreak: 90% resisted" in result.err
    assert "System Prompt Leak: 100% resisted (before: 95%)" in result.err
    started = platform.security_runs[0]
    assert started["judge"]["model"] == "gpt-4o-mini"
    assert len(started["models"]) == 2


def test_a_failing_category_exits_with_2_under_ci_and_is_named(
    platform: FakePlatform, run: Run, tmp_path: Path
) -> None:
    pushed(platform, run, tmp_path, JUDGED)
    message = "System prompt leak: resisted attacks fell from 100% to 30%; at most 5% may be lost."
    with_pack(platform, **gate(False, [category("system_prompt_leak", 0.3, 1.0)], [message]))
    ci = run("run", "--security", "--ci")
    assert ci.code == 2
    assert message in ci.err
    assert "The security gate failed for: tag." in ci.err
    warned = run("run", "--security", "--yes")  # without --ci the security gate only warns
    assert warned.code == 0
    assert "The security gate would fail for: tag." in warned.err


def test_the_minimum_is_sent_to_the_server_and_the_default_is_80_percent(
    platform: FakePlatform, run: Run, tmp_path: Path
) -> None:
    pushed(platform, run, tmp_path, JUDGED)
    with_pack(platform, **gate(True, [category("jailbreak", 0.9)], []))
    run("run", "--security", "--yes", "--security-min", "0.95")
    assert platform.security_gate_queries[-1]["min_pass_rate"] == "0.95"
    run("run", "--security", "--yes")
    assert platform.security_gate_queries[-1]["min_pass_rate"] == "0.8"


def test_without_an_approved_pack_or_a_judge_it_says_what_to_do(
    platform: FakePlatform, run: Run, tmp_path: Path
) -> None:
    pushed(platform, run, tmp_path, JUDGED)
    none = run("run", "--security", "--yes")
    assert none.code == 1
    assert "no approved security pack" in none.err.lower()
    assert "Security screen" in none.err
    nojudge_dir = tmp_path / "other"
    nojudge_dir.mkdir()
    with_pack(platform, **gate(True, [], []))
    (tmp_path / "verano.yaml").write_text((tmp_path / "verano.yaml").read_text().replace(JUDGED, ""))
    missing = run("run", "--security", "--yes")
    assert missing.code == 1
    assert "judge" in missing.err.lower()
