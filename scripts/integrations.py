"""
The integration registry: check it, and generate everything that shows it.

    cd backend && PYTHONPATH=. uv run python ../scripts/integrations.py COMMAND

    check      validate docs/integrations/registry.yaml
    write      regenerate the README block and docs/integrations/README.md
    json       the registry with its logos, for the website and the comparison page
    logos DIR  copy the logos the registry uses from an unpacked simple-icons package

`docs/integrations/registry.yaml` is the single source. A row needs the evidence for its status (a test for
"sample_tested", a recorded real check for "validated", a next step for "planned"), so nothing is listed as an
integration because it is only theoretically compatible. Logos are the real marks from Simple Icons, kept in
docs/assets/logos with their sources and licences in CREDITS.md; a brand with no mark gets a short text chip.
"""

import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "docs/integrations/registry.yaml"
LOGOS = ROOT / "docs/assets/logos"
README = ROOT / "README.md"
PAGE = ROOT / "docs/integrations/README.md"
START, END = "<!-- integrations:start -->", "<!-- integrations:end -->"

GROUPS = {
    "native_sdk": "Native SDKs",
    "framework_adapter": "Framework adapters",
    "observability_import": "Observability imports",
    "ci_integration": "CI integrations",
}
STATUSES = {"planned": "Planned", "built": "Built", "sample_tested": "Sample-tested", "validated": "Validated"}
MEANING = {
    "built": "the code exists; no automated test of this integration",
    "sample_tested": "automated tests pass against stand-in objects or sample files we wrote",
    "validated": "checked against the real third-party tool or library, with the version and date recorded",
    "planned": "not built",
}
EVIDENCE_KINDS = {"test", "record"}
MAX_CHIP = 5
DARK = 0.18  # brands darker than this are drawn in grey so they stay readable on a dark page
GREY = "#57606a"


def load(path: Path = REGISTRY) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return list(data["integrations"])


def problems(items: list[dict[str, Any]], root: Path = ROOT) -> list[str]:
    """Everything wrong with the registry, in plain words; empty when it is sound."""
    found: list[str] = []
    seen: set[str] = set()
    for item in items:
        name = str(item.get("id", "?"))
        if name in seen:
            found.append(f"{name}: the id is used twice")
        seen.add(name)
        for key in ("id", "name", "group", "status", "summary"):
            if not item.get(key):
                found.append(f"{name}: '{key}' is missing")
        if item.get("group") not in GROUPS:
            found.append(f"{name}: group must be one of {', '.join(GROUPS)}")
        status = item.get("status")
        if status not in STATUSES:
            found.append(f"{name}: status must be one of {', '.join(STATUSES)}")
            continue
        evidence = item.get("evidence") or []
        for entry in evidence:
            if entry.get("kind") not in EVIDENCE_KINDS or not (root / str(entry.get("ref", ""))).exists():
                found.append(f"{name}: evidence {entry.get('ref')!r} is not a test or record that exists")
        if status != "planned" and not (item.get("where") and (root / item["where"]).exists()):
            found.append(f"{name}: 'where' must name the code that exists")
        if status == "sample_tested" and not any(e.get("kind") == "test" for e in evidence):
            found.append(f"{name}: 'sample_tested' needs a test as evidence")
        if status == "validated":
            if not evidence:
                found.append(f"{name}: 'validated' needs evidence")
            for key in ("verified_with", "verified_on"):
                if not item.get(key):
                    found.append(f"{name}: 'validated' needs '{key}' (the real tool's version, and the date)")
        if status in {"planned", "built", "sample_tested"} and not item.get("next_step"):
            found.append(f"{name}: needs a 'next_step' until it is validated")
        if status == "planned" and (evidence or item.get("where")):
            found.append(f"{name}: a planned row has no code or evidence yet")
        logo = item.get("logo")
        if logo and not (root / "docs/assets/logos" / f"{logo}.svg").exists():
            found.append(f"{name}: the logo '{logo}' is not in docs/assets/logos")
        if not logo and not (item.get("chip") and len(str(item["chip"])) <= MAX_CHIP):
            found.append(f"{name}: with no logo, give a 'chip' of at most {MAX_CHIP} characters")
    return found


def counts(items: list[dict[str, Any]]) -> dict[str, int]:
    return {status: sum(1 for i in items if i["status"] == status) for status in STATUSES}


def summary_line(items: list[dict[str, Any]]) -> str:
    n = counts(items)
    return (
        f"{n['validated']} validated · {n['sample_tested']} sample-tested · {n['built']} built · {n['planned']} planned"
    )


def mark(item: dict[str, Any], prefix: str) -> str:
    if item.get("logo"):
        return f'<img src="{prefix}docs/assets/logos/{item["logo"]}.svg" alt="" width="20" height="20">'
    return f"<kbd>{item['chip']}</kbd>"


def row(item: dict[str, Any], prefix: str, link_prefix: str) -> str:
    detail = item["summary"]
    for entry in item.get("evidence") or []:
        note = f" ({entry['note']})" if entry.get("note") else ""
        detail += f" [{Path(entry['ref']).name}]({link_prefix}{entry['ref']}){note}."
    if item["status"] == "validated":
        detail += f" Checked with {item['verified_with']} on {item['verified_on']}."
    if item.get("distribution"):
        detail += f" {item['distribution'].capitalize()}."
    if item["status"] != "validated" and item.get("next_step"):
        detail += f" Next: {item['next_step']}"
    name = item["name"].replace("|", "/")
    return f"| {mark(item, prefix)} | **{name}** | {STATUSES[item['status']]} | {detail} |"


def table(items: list[dict[str, Any]], prefix: str, link_prefix: str, with_group: bool = False) -> list[str]:
    lines = ["| | Integration | Status | What it does and what shows it |", "|---|---|---|---|"]
    for item in items:
        line = row(item, prefix, link_prefix)
        if with_group:
            line = line.replace(f"**{item['name']}**", f"**{item['name']}** ({GROUPS[item['group']].lower()})", 1)
        lines.append(line)
    return lines


def legend() -> list[str]:
    return [f"- **{STATUSES[s]}:** {MEANING[s]}." for s in ("validated", "sample_tested", "built", "planned")]


def render(items: list[dict[str, Any]], prefix: str, link_prefix: str, heading_level: int, intro: bool) -> str:
    """The integration tables as Markdown. `prefix` is the path from the file to the repository root."""
    hashes = "#" * heading_level
    out: list[str] = []
    if intro:
        out += [
            "Every integration below shows what has been checked, not what might work. Nothing is listed because "
            "it is only theoretically compatible (for example, through OpenTelemetry): a row needs the evidence "
            "for its status.",
            "",
            *legend(),
            "",
            f"Today: {summary_line(items)}.",
            "",
        ]
    for group, title in GROUPS.items():
        members = [i for i in items if i["group"] == group and i["status"] != "planned"]
        if members:
            out += [f"{hashes} {title}", "", *table(members, prefix, link_prefix), ""]
    planned = [i for i in items if i["status"] == "planned"]
    out += [f"{hashes} Planned", "", *table(planned, prefix, link_prefix, with_group=True), ""]
    out += [
        "Logos are the marks of their owners, shown only to say what works with Verano; it is not an endorsement. "
        "Sources and licences: [logo credits](" + prefix + "docs/assets/logos/CREDITS.md).",
    ]
    return "\n".join(out).rstrip() + "\n"


def readme_block(items: list[dict[str, Any]]) -> str:
    body = render(items, "", "", heading_level=3, intro=True)
    return f"{START}\n{body}{END}"


def page(items: list[dict[str, Any]]) -> str:
    head = (
        "# Integrations\n\n"
        "Generated from [`registry.yaml`](registry.yaml) by `make integrations`; do not edit by hand.\n\n"
    )
    return head + render(items, "../../", "../../", heading_level=2, intro=True)


def with_block(readme: str, items: list[dict[str, Any]]) -> str:
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.DOTALL)
    if not pattern.search(readme):
        raise SystemExit(f"README.md needs the markers {START} and {END} where the integrations go.")
    return pattern.sub(lambda _: readme_block(items), readme, count=1)


def luminance(hex_color: str) -> float:
    r, g, b = (int(hex_color[i : i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def sync_logos(package: Path) -> list[str]:
    """Copy the logos the registry uses from an unpacked simple-icons package, coloured, and write CREDITS.md."""
    wanted = sorted({i["logo"] for i in load() if i.get("logo")})
    info = {entry["slug"]: entry for entry in json.loads((package / "data/simple-icons.json").read_text())}
    LOGOS.mkdir(parents=True, exist_ok=True)
    credits = [
        "# Logo credits\n",
        "The marks below come from [Simple Icons](https://simpleicons.org) (the files are CC0). **Each mark remains "
        "the trademark of its owner**, and some have their own licence, listed here. They are shown only to say "
        "what works with Verano; it is not an endorsement. Brand guidelines of each owner apply.\n",
        "| Mark | Brand | Source | Guidelines | Licence |",
        "|---|---|---|---|---|",
    ]
    for slug in wanted:
        entry = info[slug]
        color = f"#{entry['hex']}" if luminance(entry["hex"]) >= DARK else GREY
        svg = (package / "icons" / f"{slug}.svg").read_text().replace("<svg ", f'<svg fill="{color}" ', 1)
        (LOGOS / f"{slug}.svg").write_text(svg)
        licence = (entry.get("license") or {}).get("type") or "see the owner's guidelines"
        credits.append(
            f"| {slug} | {entry['title']} | {entry.get('source', '')} | {entry.get('guidelines', '')} | {licence} |"
        )
    (LOGOS / "CREDITS.md").write_text("\n".join(credits) + "\n")
    return wanted


def as_json(items: list[dict[str, Any]]) -> str:
    out = []
    for item in items:
        svg = (LOGOS / f"{item['logo']}.svg").read_text() if item.get("logo") else None
        out.append({**{k: v for k, v in item.items() if k != "logo"}, "logo": item.get("logo"), "svg": svg})
    return json.dumps({"statuses": STATUSES, "groups": GROUPS, "integrations": out}, indent=2, ensure_ascii=False)


def main(argv: list[str]) -> int:
    command = argv[1] if len(argv) > 1 else "check"
    items = load()
    if command == "logos":
        copied = sync_logos(Path(argv[2]))
        print(f"Copied {len(copied)} logos: {', '.join(copied)}")
        return 0
    errors = problems(items)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    if command == "check":
        print(f"Registry is sound: {summary_line(items)}.")
        return 0
    if command == "write":
        README.write_text(with_block(README.read_text(encoding="utf-8"), items), encoding="utf-8")
        PAGE.write_text(page(items), encoding="utf-8")
        print("README.md and docs/integrations/README.md are up to date.")
        return 0
    if command == "json":
        print(as_json(items))
        return 0
    print(f"Unknown command {command!r}: use check, write, json or logos DIR.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
