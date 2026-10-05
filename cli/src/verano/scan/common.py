"""
What every scanner shares: how a prompt is held (`Text`), how text becomes a Verano template safely,
how a provider is told from a model name, and how messages become the system and user prompt.
"""

import re
import string
from dataclasses import dataclass, field
from typing import Any

from verano.scan.findings import KNOWN_PARAMS, Finding

PROVIDER_PREFIXES = {
    "openai": "openai", "anthropic": "anthropic", "gemini": "gemini", "groq": "groq", "xai": "xai",
    "mistral": "mistral", "together_ai": "together", "together": "together", "openrouter": "openrouter",
    "ollama": "ollama", "ollama_chat": "ollama",
}  # fmt: skip
MODEL_STARTS = {
    "gpt-": "openai", "chatgpt": "openai", "o1": "openai", "o3": "openai", "o4": "openai", "claude": "anthropic",
    "gemini": "gemini", "grok": "xai", "mistral": "mistral", "mixtral": "mistral", "codestral": "mistral",
}  # fmt: skip
LANGCHAIN_MODELS = {
    "ChatOpenAI": "openai", "ChatAnthropic": "anthropic", "ChatGoogleGenerativeAI": "gemini", "ChatGroq": "groq",
    "ChatMistralAI": "mistral", "ChatOllama": "ollama", "ChatXAI": "xai", "ChatTogether": "together",
}  # fmt: skip
PARAM_ALIASES = {
    "temperature": "temperature", "top_p": "top_p", "topP": "top_p", "top_k": "top_k", "topK": "top_k",
    "seed": "seed", "max_tokens": "max_tokens", "maxTokens": "max_tokens", "max_completion_tokens": "max_tokens",
    "max_output_tokens": "max_tokens", "maxOutputTokens": "max_tokens", "maxCompletionTokens": "max_tokens",
    "stop": "stop", "stop_sequences": "stop", "stopSequences": "stop",
}  # fmt: skip
SPECIAL = re.compile(r"\{[{%#]")
MAX_DEPTH = 6


def escape(text: str) -> str:
    """Text that Verano's template would read as a placeholder or tag is written as a literal."""
    return SPECIAL.sub(lambda m: "{{ '" + m.group(0) + "' }}", text)


def infer_provider(model: str | None) -> tuple[str | None, str | None]:
    """The provider and the model name without a `provider/` prefix, as far as the name says."""
    if not model:
        return None, None
    if "/" in model:
        prefix, rest = model.split("/", 1)
        if prefix.lower() in PROVIDER_PREFIXES:
            return PROVIDER_PREFIXES[prefix.lower()], rest
    lowered = model.lower()
    for start, provider in MODEL_STARTS.items():
        if lowered.startswith(start):
            return provider, model
    return None, model


@dataclass
class Text:
    text: str = ""
    variables: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    def add(self, other: "Text") -> None:
        self.text += other.text
        for name in other.variables:
            if name not in self.variables:
                self.variables.append(name)
        self.problems += [p for p in other.problems if p not in self.problems]


def variable(name: str) -> Text:
    return Text("{{ " + name + " }}", [name])


def identifier_from(source: str) -> str:
    """A variable name for an expression that is not a plain name: its text with symbols turned to `_`."""
    return re.sub(r"[^A-Za-z0-9_]+", "_", source).strip("_")[:40] or "value"


def assemble(finding: Finding, system: Text, user: Text) -> None:
    """Puts the two prompts and their variables on the finding; what could not be read becomes problems."""
    finding.system = system.text.strip() or None
    finding.user = user.text.strip() or None
    for text in (system, user):
        for name in text.variables:
            if name not in finding.variables:
                finding.variables.append(name)
        finding.problems += [f"the prompt {p}" for p in text.problems if f"the prompt {p}" not in finding.problems]


def apply_messages(messages: list[tuple[str, Text]], finding: Finding) -> None:
    """(role, text) pairs as one system prompt and the last user message; earlier turns are mentioned only."""
    system = Text()
    for role, text in messages:
        if role in {"system", "developer"}:
            if system.text:
                system.text += "\n\n"
            system.add(text)
    users = [i for i, (role, _) in enumerate(messages) if role == "user"]
    user = messages[users[-1]][1] if users else Text()
    earlier = len(messages) - (1 if users else 0) - sum(1 for r, _ in messages if r in {"system", "developer"})
    if earlier > 0:
        finding.notes.append(f"{earlier} earlier example messages (few-shot) are not included.")
    assemble(finding, system, user)


def store_param(finding: Finding, key: str, value: Any, source: str) -> None:
    """A setting written as a plain value goes into `params`; anything else is a note, not a guess."""
    target = PARAM_ALIASES.get(key)
    if target is None:
        return
    if value is None or (target == "stop" and not isinstance(value, str | list)):
        finding.notes.append(f"{key} is not a fixed value (`{source[:40]}`); left out.")
    elif target == "stop":
        finding.params[target] = [value] if isinstance(value, str) else value
    elif target in KNOWN_PARAMS and not isinstance(value, str):
        finding.params[target] = value


def format_template(raw: str) -> Text:
    """A `{name}` style template (str.format, LangChain) as a Verano template."""
    out = Text()
    try:
        parsed = list(string.Formatter().parse(raw))
    except ValueError:
        return Text(escape(raw), problems=["has braces that don't form a valid template"])
    unnamed = 0
    for literal, field_name, _spec, _conv in parsed:
        out.text += escape(literal)
        if field_name is None:
            continue
        if field_name == "" or field_name.isdigit():
            name = f"arg{unnamed}" if field_name == "" else f"arg{field_name}"
            unnamed += 1
        else:
            base = re.split(r"[.\[]", field_name, maxsplit=1)[0]
            name = base if base.isidentifier() else identifier_from(field_name)
            if base != field_name:
                out.problems.append(f"uses the expression `{{{field_name}}}`")
        out.add(Text("{{ " + name + " }}", [name]))
    return out
