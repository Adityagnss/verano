"""
What a scan finds, and how a finding becomes an entry of verano.yaml.

A finding is one place where code calls a model or builds a prompt. It carries the file and line,
the model and settings that are written as plain values, the prompt text turned into Verano's
`{{ variable }}` form, and `problems`: the reasons it can't be used as is. Nothing is guessed:
what could not be read is listed, not filled in.

Verano tests a prompt on real examples that arrive as one input (`attachment`). So a prompt with
exactly one variable has it renamed to `attachment`; a prompt with several can't run on real test
cases yet and is offered unticked, with the reason.
"""

import re
from dataclasses import dataclass, field
from typing import Any

from verano.spec import NAME

ATTACHMENT = "attachment"
PROVIDER_KEYS = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "groq": "GROQ_API_KEY",
    "xai": "XAI_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "together": "TOGETHER_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}
KNOWN_PARAMS = ("temperature", "top_p", "top_k", "max_tokens", "seed", "stop")


@dataclass
class Finding:
    file: str
    line: int
    kind: str = "call"  # "call": a model call, "prompt": a prompt template with no call next to it
    provider: str | None = None
    model: str | None = None
    system: str | None = None
    user: str | None = None
    variables: list[str] = field(default_factory=list)
    params: dict[str, Any] = field(default_factory=dict)
    function: str | None = None
    notes: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    @property
    def where(self) -> str:
        return f"{self.file}:{self.line}"

    @property
    def has_prompt(self) -> bool:
        return bool(self.system or self.user)

    @property
    def usable(self) -> bool:
        """Found a prompt and nothing was left unread."""
        return self.has_prompt and not self.problems

    @property
    def runnable(self) -> bool:
        return self.usable and len(self.variables) <= 1


@dataclass
class Entry:
    """A finding in the shape of a verano.yaml prompt entry."""

    name: str
    finding: Finding
    system: str | None
    user: str | None
    runnable: bool
    reason: str | None
    comments: list[str] = field(default_factory=list)


def slug(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", text.replace("_", "-")).strip("-").lower()
    return cleaned or "prompt"


def entry_name(finding: Finding, taken: set[str]) -> str:
    stem = finding.file.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    base = slug(finding.function) if finding.function else f"{slug(stem)}-{finding.line}"
    base = base[:60]
    if not NAME.match(base):
        base = f"prompt-{finding.line}"
    name, number = base, 2
    while name in taken:
        name, number = f"{base}-{number}", number + 1
    taken.add(name)
    return name


def _rename(text: str | None, old: str, new: str) -> str | None:
    if text is None:
        return None
    return re.sub(r"\{\{\s*" + re.escape(old) + r"\s*\}\}", "{{ " + new + " }}", text)


def to_entry(finding: Finding, taken: set[str]) -> Entry:
    """Applies the one-input rule and decides whether the entry can be ticked."""
    name = entry_name(finding, taken)
    system, user = finding.system, finding.user
    comments = list(finding.notes)
    if len(finding.variables) == 1:
        (only,) = finding.variables
        if only != ATTACHMENT:
            system, user = _rename(system, only, ATTACHMENT), _rename(user, only, ATTACHMENT)
            comments.append(f"`{only}` is now `{ATTACHMENT}`: each test case's input is sent there.")
        if user is not None and user.strip() == "{{ " + ATTACHMENT + " }}":
            user = None  # only the input: a system-only prompt, where the input is the user message
    reason = None
    if finding.problems:
        reason = "; ".join(finding.problems)
    elif not finding.has_prompt:
        reason = "no prompt text was found"
    elif len(finding.variables) > 1:
        names = ", ".join(finding.variables)
        reason = (
            f"it has {len(finding.variables)} inputs ({names}); "
            "real test cases supply one, so it can't be run on them yet"
        )
    return Entry(name, finding, system, user, finding.runnable, reason, comments)


@dataclass
class ScanResult:
    findings: list[Finding] = field(default_factory=list)
    files_scanned: int = 0
    files_skipped: list[str] = field(default_factory=list)
    other: list[str] = field(default_factory=list)  # things found that Verano can't test yet: tools, retrieval, ...
    data_files: list[str] = field(default_factory=list)
