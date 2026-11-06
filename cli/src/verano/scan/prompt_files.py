"""
Prompts kept in files of their own: `.txt`, `.md`, `.jinja` (also `.jinja2`, `.j2`) and `.yaml`/`.yml`.

A text file counts only when it sits in a folder named like `prompts/` or its name says "prompt",
so a README is never mistaken for one. A YAML file counts only when it has prompt-shaped keys
(`system`, `user`, `prompt`, `template`, `instructions`, or `messages` with roles). The text is
read as it is; `{{ variable }}` placeholders are the inputs. These are found by their names, not
understood, so every finding is "broad" (offered unticked, to be checked by a person) and carries
a note saying how it was read. Nothing is sent anywhere.
"""

import re
from pathlib import Path
from typing import Any

import yaml

from verano.scan import walk
from verano.scan.findings import Finding

TEXT_SUFFIXES = {".txt", ".md", ".jinja", ".jinja2", ".j2"}
YAML_SUFFIXES = {".yaml", ".yml"}
SUFFIXES = TEXT_SUFFIXES | YAML_SUFFIXES
PROMPT_DIRS = {"prompt", "prompts", "prompt_templates", "prompt-templates", "templates"}
NOT_PROMPTS = {"readme", "changelog", "license", "contributing", "code_of_conduct", "security", "verano"}
SYSTEM_KEYS = ("system", "system_prompt", "system_message", "instructions")
USER_KEYS = ("user", "user_prompt", "user_message", "prompt", "template")
PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)")
LOGIC = re.compile(r"\{%")
MAX_YAML_DOCUMENTS = 1


def _variables(*texts: str | None) -> list[str]:
    found: list[str] = []
    for text in texts:
        for name in PLACEHOLDER.findall(text or ""):
            if name not in found:
                found.append(name)
    return found


def _looks_like_prompt_file(relative: Path) -> bool:
    stem = relative.stem.lower()
    if stem in NOT_PROMPTS or any(part.startswith(".") for part in relative.parts[:-1]):
        return False
    in_prompt_folder = any(part.lower() in PROMPT_DIRS for part in relative.parts[:-1])
    return in_prompt_folder or "prompt" in stem


def _text_finding(path: Path, relative: str) -> Finding | None:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return None
    stem = Path(relative).stem.lower()
    names_user = "user" in stem and "system" not in stem
    finding = Finding(file=relative, line=1, kind="prompt", level="broad", function=Path(relative).stem)
    if names_user:
        finding.user = text
        finding.notes.append("read as the user prompt because of the file name")
    else:
        finding.system = text
        finding.notes.append("read as the system prompt: the whole file")
    finding.variables = _variables(text)
    if LOGIC.search(text):
        finding.notes.append("uses Jinja logic ({% ... %}); check it renders with only the inputs you give")
    return finding


def _message_texts(messages: Any) -> tuple[str | None, str | None]:
    system: list[str] = []
    user: list[str] = []
    for message in messages if isinstance(messages, list) else []:
        if isinstance(message, dict) and isinstance(message.get("content"), str):
            role = str(message.get("role", "")).lower()
            if role in {"system", "developer"}:
                system.append(message["content"])
            elif role == "user":
                user.append(message["content"])
    return "\n\n".join(system) or None, "\n\n".join(user) or None


def _yaml_finding(path: Path, relative: str) -> Finding | None:
    try:
        documents = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
    except (yaml.YAMLError, UnicodeDecodeError):
        return None
    if len(documents) != MAX_YAML_DOCUMENTS or not isinstance(documents[0], dict):
        return None
    data: dict[str, Any] = documents[0]
    system = next((data[k] for k in SYSTEM_KEYS if isinstance(data.get(k), str)), None)
    user = next((data[k] for k in USER_KEYS if isinstance(data.get(k), str)), None)
    if system is None and user is None:
        system, user = _message_texts(data.get("messages"))
    if system is None and user is None:
        return None
    label = data.get("name")
    finding = Finding(
        file=relative,
        line=1,
        kind="prompt",
        level="broad",
        system=system,
        user=user,
        variables=_variables(system, user),
        function=label if isinstance(label, str) else Path(relative).stem,
    )
    finding.notes.append("read from the YAML keys; check which text is the system prompt and which the user prompt")
    model = data.get("model")
    if isinstance(model, str):
        finding.model = model
    params = data.get("parameters") or data.get("params")
    if isinstance(params, dict):
        finding.params = {
            k: v for k, v in params.items() if k in ("temperature", "top_p", "top_k", "max_tokens", "seed")
        }
    return finding


def scan_prompt_files(root: Path) -> tuple[list[Finding], list[str], int]:
    """The findings, the files that were skipped (with the reason), and how many files were read."""
    findings: list[Finding] = []
    skipped: list[str] = []
    read = 0
    for path in walk.source_files(root, SUFFIXES):
        relative = path.relative_to(root)
        is_yaml = path.suffix.lower() in YAML_SUFFIXES
        if not is_yaml and not _looks_like_prompt_file(relative):
            continue
        if walk.too_big(path):
            skipped.append(f"{relative.as_posix()}: larger than 1 MB")
            continue
        try:
            finding = _yaml_finding(path, relative.as_posix()) if is_yaml else _text_finding(path, relative.as_posix())
        except (OSError, UnicodeDecodeError):
            skipped.append(f"{relative.as_posix()}: not UTF-8 text")
            continue
        if finding is not None:
            read += 1
            findings.append(finding)
    return findings, skipped, read
