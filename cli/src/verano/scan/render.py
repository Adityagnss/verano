"""
Writes the verano.yaml that `verano init` proposes.

By hand, not with a YAML library, so prompts stay readable (block text), every guess is marked
`TODO`, and the entries you did not tick stay in the file as comments, with the reason. The
result must load: a test reads it back with the real loader and compares the prompt text.
"""

import json
from typing import Any

from verano.scan.findings import PROVIDER_KEYS, Entry

HEADER = """\
# verano.yaml, proposed by `verano init` from your code. Nothing was sent anywhere.
# Look for TODO, then run `verano validate` and `verano push --dry-run`.
"""
TASK_TYPES = "classification, extraction, summarization, question_answering, generation, transformation, conversation"
PLACEHOLDER_MODEL = "TODO-model"


def scalar(text: str) -> str:
    """A one-line YAML string (always double-quoted JSON, which YAML reads as is)."""
    return json.dumps(text, ensure_ascii=False)


def _block_safe(text: str) -> bool:
    first = text.split("\n", 1)[0]
    odd = any((ord(c) < 32 and c not in "\n") or 0x7F <= ord(c) <= 0x9F or c in "  ﻿" for c in text)
    return not odd and not first.startswith((" ", "\t")) and "\t" not in text and text == text.strip()


def text_lines(key: str, text: str, indent: str) -> list[str]:
    if "\n" in text and _block_safe(text):
        return [f"{indent}{key}: |-", *[f"{indent}  {line}" if line else "" for line in text.split("\n")]]
    return [f"{indent}{key}: {scalar(text)}"]


def flow(value: Any) -> str:
    if isinstance(value, list):
        return "[" + ", ".join(flow(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{" + ", ".join(f"{k}: {flow(v)}" for k, v in value.items()) + "}"
    return json.dumps(value, ensure_ascii=False)


def entry_lines(entry: Entry) -> list[str]:
    finding = entry.finding
    lines = [f"- name: {entry.name}", f"  source: {{file: {scalar(finding.file)}, line: {finding.line}}}"]
    if entry.system:
        lines += text_lines("system", entry.system, "  ")
    if entry.user:
        lines += text_lines("user", entry.user, "  ")
    if finding.params:
        lines.append(f"  params: {flow(finding.params)}")
    lines += [
        "  task:",
        f"    type: generation  # TODO: {TASK_TYPES}",
        '    goal: "TODO: say what this prompt should do"',
        "    # allowed_outputs: [a, b]   # required for classification",
        "  # data:   # TODO: your own examples; each row becomes a test case",
        "  #   cases: {file: data/examples.csv, input: text, expected: expected}",
    ]
    model = finding.model or PLACEHOLDER_MODEL
    todo = "  # TODO: the model was not found in the code" if finding.model is None else ""
    lines.append(f"  models: [{scalar(model)}]{todo}")
    return lines


def render(project: str, chosen: list[Entry], skipped: list[Entry]) -> str:
    keys = sorted({e.finding.provider for e in chosen if e.finding.provider in PROVIDER_KEYS if e.finding.provider})
    out = [HEADER, "version: 1", f"project: {scalar(project)}"]
    if keys:
        out += ["keys:", *[f"  {p}: env:{PROVIDER_KEYS[p]}" for p in keys]]
    else:
        out.append("# keys:   # name the environment variable of each provider's key, e.g. openai: env:OPENAI_API_KEY")
    out.append("prompts:")
    for entry in chosen:
        for note in entry.comments:
            out.append(f"  # {note}")
        out += [f"  {line}" if line else "" for line in entry_lines(entry)]
        out.append("")
    for entry in skipped:
        out.append(f"  # Not included: {entry.name} ({entry.finding.where}): {entry.reason or 'not selected'}")
        out += [f"  # {line}" if line else "  #" for line in entry_lines(entry)]
        out.append("")
    return "\n".join(out).rstrip() + "\n"
