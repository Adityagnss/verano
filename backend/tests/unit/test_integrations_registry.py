"""The integration registry (docs/integrations/registry.yaml): every row has the evidence its status needs, every logo
exists, and the README block and the integrations page are exactly what the registry generates (so a surface cannot
drift from it). The rules live in scripts/integrations.py."""

import copy
import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[3]


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("integrations_script", ROOT / "scripts/integrations.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


script = load_script()


def good() -> list[dict[str, Any]]:
    return copy.deepcopy(script.load())


def test_the_registry_is_sound() -> None:
    assert script.problems(script.load()) == []


def test_the_readme_and_the_page_are_what_the_registry_generates() -> None:
    items = script.load()
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert script.with_block(readme, items) == readme, "run `make integrations`"
    assert (ROOT / "docs/integrations/README.md").read_text(encoding="utf-8") == script.page(items)


def test_no_row_claims_more_than_its_evidence_shows() -> None:
    for item in script.load():
        if item["status"] == "validated":
            assert item["verified_with"] and item["verified_on"]
        if item["status"] == "sample_tested":
            assert any(e["kind"] == "test" for e in item["evidence"]), item["id"]
        if item["status"] == "planned":
            assert "evidence" not in item and "where" not in item, item["id"]


def mutate(change: Any) -> list[str]:
    items = good()
    change(items)
    found: list[str] = script.problems(items)
    return found


def test_a_sample_tested_row_without_a_test_is_refused() -> None:
    def change(items: list[dict[str, Any]]) -> None:
        next(i for i in items if i["id"] == "python-sdk")["evidence"] = []

    assert any("needs a test as evidence" in p for p in mutate(change))


def test_a_validated_row_needs_the_real_tools_version_and_the_date() -> None:
    def change(items: list[dict[str, Any]]) -> None:
        row = next(i for i in items if i["id"] == "pytest-plugin")
        del row["verified_with"], row["verified_on"]

    found = mutate(change)
    assert any("verified_with" in p for p in found) and any("verified_on" in p for p in found)


def test_promoting_a_planned_row_without_evidence_is_refused() -> None:
    def change(items: list[dict[str, Any]]) -> None:
        row = next(i for i in items if i["id"] == "go-sdk")
        row["status"] = "sample_tested"

    found = mutate(change)
    assert any("'where' must name the code that exists" in p for p in found)
    assert any("needs a test as evidence" in p for p in found)


def test_evidence_must_point_at_a_file_that_exists() -> None:
    def change(items: list[dict[str, Any]]) -> None:
        next(i for i in items if i["id"] == "python-sdk")["evidence"] = [{"kind": "test", "ref": "sdk/nope.py"}]

    assert any("not a test or record that exists" in p for p in mutate(change))


def test_a_row_needs_a_next_step_until_it_is_validated() -> None:
    def change(items: list[dict[str, Any]]) -> None:
        del next(i for i in items if i["id"] == "github-action")["next_step"]

    assert any("needs a 'next_step'" in p for p in mutate(change))


def test_a_logo_must_exist_and_without_one_a_short_chip_is_needed() -> None:
    def missing_logo(items: list[dict[str, Any]]) -> None:
        next(i for i in items if i["id"] == "python-sdk")["logo"] = "no-such-brand"

    def no_chip(items: list[dict[str, Any]]) -> None:
        row = next(i for i in items if i["id"] == "har")
        del row["chip"]

    assert any("is not in docs/assets/logos" in p for p in mutate(missing_logo))
    assert any("give a 'chip'" in p for p in mutate(no_chip))


def test_ids_are_unique_and_groups_and_statuses_are_known() -> None:
    def change(items: list[dict[str, Any]]) -> None:
        items.append(copy.deepcopy(items[0]))
        items[1]["group"] = "plugins"
        items[2]["status"] = "works-probably"

    found = mutate(change)
    assert any("used twice" in p for p in found)
    assert any("group must be one of" in p for p in found)
    assert any("status must be one of" in p for p in found)


def test_every_logo_has_a_credit_line_and_the_counts_add_up() -> None:
    credits = (ROOT / "docs/assets/logos/CREDITS.md").read_text(encoding="utf-8")
    for item in script.load():
        if item.get("logo"):
            assert f"| {item['logo']} |" in credits, item["logo"]
    items = script.load()
    assert sum(script.counts(items).values()) == len(items)
