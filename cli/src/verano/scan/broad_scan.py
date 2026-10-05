"""
The Broad level: Java, Go, C#, Ruby, PHP, Rust, Kotlin and Swift (medium accuracy).

These languages have too many SDKs to read each call properly, so this level does not claim to.
It parses the file (tree-sitter) only to find string literals and the function around them, then
uses clues a person would use: a model name written as a whole string ("gpt-4o"), an SDK name in
an import, an API address, and long sentences near the model name. The longest sentence written
like instructions becomes `system`, the next one `user`; interpolation (`#{x}`, `$x`, `\\(x)`,
`{x}`, `%s`) becomes `{{ variables }}`. Settings (temperature and so on) are not read here.

Because the role and the text are guessed from clues, every finding is marked "found by clues" and
is offered unticked: `init --yes` never writes one without you choosing it.
"""

import re
import textwrap
from dataclasses import dataclass
from functools import cache

from tree_sitter import Language, Node, Parser

from verano.scan.common import Text, escape, identifier_from, infer_provider, variable
from verano.scan.findings import Finding

MODEL_NAME = re.compile(
    r"^(?:gpt-[\w.\-]+|chatgpt-[\w.\-]+|o[134](?:-[\w.\-]+)?|claude-[\w.\-]+|gemini-[\w.\-]+|grok-[\w.\-]+"
    r"|mistral-[\w.\-]+|mixtral-[\w.\-]+|codestral[\w.\-]*|llama[\w.\-:]*|qwen[\w.\-:]*)$",
    re.I,
)
AMBIGUOUS = re.compile(r"^(?:llama|qwen)", re.I)
URL_HINTS = {
    "api.openai.com": "openai", "api.anthropic.com": "anthropic", "generativelanguage.googleapis.com": "gemini",
    "api.groq.com": "groq", "api.mistral.ai": "mistral", "api.x.ai": "xai", "api.together.xyz": "together",
    "openrouter.ai": "openrouter",
}  # fmt: skip
SDK_HINTS = {
    "openai": "openai", "anthropic": "anthropic", "generativeai": "gemini", "genai": "gemini", "groq": "groq",
    "mistral": "mistral", "ollama": "ollama",
}  # fmt: skip
SYSTEM_CUE = re.compile(
    r"^\s*(?:you are|act as|your (?:task|role|job)|as an? )|\b(?:respond|reply|answer)\s+(?:with|only|in)\b"
    r"|\bclassify\b|\bsummari[sz]e\b",
    re.I,
)
EXTRA_NOTE = "found by clues, not by reading the call; check the prompt text, its role and the model."
WINDOW_LINES = 40
MIN_CHARS, MIN_WORDS = 40, 5
MAX_PROMPTS = 2


@dataclass(frozen=True)
class Lang:
    name: str
    module: str
    function: str
    strings: frozenset[str]
    functions: frozenset[str]
    style: str


def _lang(
    name: str, module: str, strings: set[str], functions: set[str], style: str, function: str = "language"
) -> Lang:
    return Lang(name, module, function, frozenset(strings), frozenset(functions), style)


_KOTLIN = _lang(
    "Kotlin", "tree_sitter_kotlin", {"string_literal", "multiline_string_literal"}, {"function_declaration"}, "kotlin"
)
LANGS: dict[str, Lang] = {
    ".java": _lang(
        "Java", "tree_sitter_java", {"string_literal"},
        {"method_declaration", "constructor_declaration", "lambda_expression"}, "printf",
    ),
    ".go": _lang(
        "Go", "tree_sitter_go", {"interpreted_string_literal", "raw_string_literal"},
        {"function_declaration", "method_declaration", "func_literal"}, "printf",
    ),
    ".cs": _lang(
        "C#", "tree_sitter_c_sharp",
        {"string_literal", "verbatim_string_literal", "raw_string_literal", "interpolated_string_expression"},
        {"method_declaration", "local_function_statement", "constructor_declaration", "lambda_expression"}, "csharp",
    ),
    ".rb": _lang("Ruby", "tree_sitter_ruby", {"string", "heredoc_body"}, {"method", "singleton_method"}, "ruby"),
    ".php": _lang(
        "PHP", "tree_sitter_php", {"string", "encapsed_string", "heredoc"},
        {"function_definition", "method_declaration", "anonymous_function"}, "php", "language_php",
    ),
    ".rs": _lang(
        "Rust", "tree_sitter_rust", {"string_literal", "raw_string_literal"},
        {"function_item", "closure_expression"}, "rust",
    ),
    ".kt": _KOTLIN,
    ".kts": _KOTLIN,
    ".swift": _lang(
        "Swift", "tree_sitter_swift", {"line_string_literal", "multi_line_string_literal"},
        {"function_declaration", "init_declaration"}, "swift",
    ),
}  # fmt: skip
SUFFIXES = set(LANGS)


@cache
def parser_for(suffix: str) -> Parser:
    """Loaded on first use, so a command that never scans doesn't pay for eight grammars."""
    import importlib

    lang = LANGS[suffix]
    module = importlib.import_module(lang.module)
    return Parser(Language(getattr(module, lang.function)()))


def txt(node: Node) -> str:
    return node.text.decode("utf-8", "replace") if node.text else ""


# -- string bodies -----------------------------------------------------------------------------------

SIMPLE_ESCAPES = {"n": "\n", "r": "\r", "t": "\t", '"': '"', "'": "'", "\\": "\\", "0": "\0", "$": "$", "`": "`"}


def unescape(body: str) -> str:
    return re.sub(r"\\(.)", lambda m: SIMPLE_ESCAPES.get(m.group(1), m.group(0)), body, flags=re.S)


def body_of(raw: str, style: str, node_type: str) -> tuple[str, bool]:
    """The text between a literal's quotes, and whether it can contain interpolation."""
    text = raw
    interpolated = style in {"ruby", "kotlin", "swift", "php", "printf"}
    if style == "csharp":
        interpolated = text.startswith("$") or node_type == "interpolated_string_expression"
        text = text.lstrip("$@")
    if text.startswith(("<<~", "<<-", "<<<", "<<")) or node_type in {"heredoc_body", "heredoc"}:
        lines = text.split("\n")
        if lines and lines[0].startswith("<<"):
            lines = lines[1:]
        if lines and re.fullmatch(r"\s*[A-Z_]+;?\s*", lines[-1]):
            lines = lines[:-1]
        return textwrap.dedent("\n".join(lines)).strip(), True
    for quote in ('"""', "'''"):
        if text.startswith(quote) and text.endswith(quote) and len(text) >= 6:
            inner = text[3:-3]
            return textwrap.dedent(inner.lstrip("\n")).strip(), interpolated
    if style == "rust" and text.startswith("r"):
        match = re.fullmatch(r'r(#*)"(.*)"\1', text, re.S)
        return (match.group(2) if match else text), False
    if text.startswith("`") and text.endswith("`"):
        return text[1:-1], False
    if text[:1] in {'"', "'"} and text[-1:] == text[:1] and len(text) >= 2:
        inner = text[1:-1]
        if style == "csharp" and raw.lstrip("$").startswith("@"):
            return inner.replace('""', '"'), interpolated
        if style == "php" and text[0] == "'":
            return inner.replace("\\'", "'").replace("\\\\", "\\"), False
        if style == "ruby" and text[0] == "'":
            return inner, False
        return unescape(inner), interpolated
    return text, interpolated


def _name_or_expression(source: str, text: Text) -> str:
    source = source.strip()
    if re.fullmatch(r"[A-Za-z_]\w*", source):
        return source
    name = identifier_from(source)
    text.problems.append(f"uses the expression `{source[:50]}`")
    return name


def _substitute(body: str, pattern: str, group: int, text: Text, flags: int = 0) -> Text:
    """Literal parts escaped, each match of `pattern` turned into a variable."""
    position = 0
    for match in re.finditer(pattern, body, flags):
        text.text += escape(body[position : match.start()])
        name = _name_or_expression(match.group(group), text)
        text.add(variable(name))
        position = match.end()
    text.text += escape(body[position:])
    return text


def interpolate(body: str, style: str, interpolated: bool, in_format_macro: bool = False) -> Text:
    """`body` as a Verano template, according to how the language writes placeholders."""
    text = Text()
    if style == "ruby" and interpolated:
        return _substitute(body, r"#\{(.*?)\}", 1, text)
    if style == "kotlin" and interpolated:
        return _kotlin(body, text)
    if style == "swift" and interpolated:
        return _substitute(body, r"\\\((.*?)\)", 1, text)
    if style == "php" and interpolated:
        return _php(body, text)
    if style == "csharp" and interpolated:
        return _csharp(body, text)
    if style == "rust" and in_format_macro:
        return _rust(body, text)
    if style == "printf":
        return _printf(body, text)
    return Text(escape(body))


def _csharp(body: str, text: Text) -> Text:
    escaped = body.replace("{{", "\0").replace("}}", "\1")
    position = 0
    for match in re.finditer(r"\{([^{}:,]+)(?:[:,][^{}]*)?\}", escaped):
        text.text += escape(escaped[position : match.start()])
        text.add(variable(_name_or_expression(match.group(1), text)))
        position = match.end()
    text.text += escape(escaped[position:])
    text.text = text.text.replace("\0", "{").replace("\1", "}")
    return text


def _kotlin(body: str, text: Text) -> Text:
    position = 0
    for match in re.finditer(r"\$\{(.*?)\}|\$([A-Za-z_]\w*)", body):
        text.text += escape(body[position : match.start()])
        name = _name_or_expression(match.group(1) or match.group(2), text)
        text.add(variable(name))
        position = match.end()
    text.text += escape(body[position:])
    return text


def _php(body: str, text: Text) -> Text:
    position = 0
    for match in re.finditer(r"\{\$([^}]+)\}|\$\{(\w+)\}|\$(\w+)(->\w+)?", body):
        text.text += escape(body[position : match.start()])
        source = match.group(1) or match.group(2) or (match.group(3) + (match.group(4) or ""))
        text.add(variable(_name_or_expression(source, text)))
        position = match.end()
    text.text += escape(body[position:])
    return text


def _rust(body: str, text: Text) -> Text:
    unnamed, position = 0, 0
    escaped = body.replace("{{", "\0").replace("}}", "\1")
    for match in re.finditer(r"\{(\w*)(?::[^}]*)?\}", escaped):
        text.text += escape(escaped[position : match.start()])
        name = match.group(1)
        if not name or name.isdigit():
            name, unnamed = f"arg{name or unnamed}", unnamed + 1
            text.problems.append("uses positional {} placeholders")
        text.add(variable(name))
        position = match.end()
    text.text += escape(escaped[position:])
    text.text = text.text.replace("\0", "{").replace("\1", "}")
    return text


def _printf(body: str, text: Text) -> Text:
    count, position = 0, 0
    for match in re.finditer(r"%(?!%)[-+# 0,(]*\d*(?:\.\d+)?[a-zA-Z]", body):
        text.text += escape(body[position : match.start()].replace("%%", "%"))
        text.add(variable(f"arg{count}"))
        text.problems.append(f"uses positional placeholders ({match.group(0)})")
        count, position = count + 1, match.end()
    text.text += escape(body[position:].replace("%%", "%"))
    return text


# -- finding clues -----------------------------------------------------------------------------------

FORMAT_MACROS = {"format", "println", "print", "eprintln", "eprint", "write", "writeln", "panic"}


@dataclass
class Literal:
    node: Node
    text: Text
    plain: str
    line: int
    function: Node | None

    @property
    def words(self) -> int:
        return len(self.plain.split())

    @property
    def promptlike(self) -> bool:
        plain = self.plain.strip()
        if re.match(r"https?://", plain) or MODEL_NAME.match(plain):
            return False
        return (len(plain) >= MIN_CHARS and self.words >= MIN_WORDS) or (bool(self.text.variables) and self.words >= 4)


class Scanner:
    def __init__(self, source: bytes, file: str, suffix: str) -> None:
        self.lang = LANGS[suffix]
        self.file = file
        self.source = source
        self.tree = parser_for(suffix).parse(source)
        self.has_error = self.tree.root_node.has_error
        self.literals = self._literals()
        self.hints = self._hints()
        self.findings: list[Finding] = []

    def _function_of(self, node: Node) -> Node | None:
        cursor = node.parent
        while cursor is not None:
            if cursor.type in self.lang.functions:
                return cursor
            cursor = cursor.parent
        return None

    def _in_format_macro(self, node: Node) -> bool:
        cursor = node.parent
        while cursor is not None and cursor.type != "source_file":
            if cursor.type == "macro_invocation":
                name = cursor.child_by_field_name("macro")
                return name is not None and txt(name) in FORMAT_MACROS
            cursor = cursor.parent
        return False

    def _literals(self) -> list[Literal]:
        found: list[Literal] = []
        stack = [self.tree.root_node]
        while stack:
            node = stack.pop()
            if node.type in self.lang.strings:
                body, interpolated = body_of(txt(node), self.lang.style, node.type)
                converted = interpolate(body, self.lang.style, interpolated, self._in_format_macro(node))
                found.append(Literal(node, converted, body, node.start_point[0] + 1, self._function_of(node)))
                continue
            stack.extend(reversed(node.children))
        return sorted(found, key=lambda lit: lit.node.start_byte)

    def _hints(self) -> set[str]:
        hints: set[str] = set()
        source = self.source.decode("utf-8", "replace").lower()
        for token, provider in SDK_HINTS.items():
            if token in source:
                hints.add(provider)
        for literal in self.literals:
            for url, provider in URL_HINTS.items():
                if url in literal.plain:
                    hints.add(provider)
        return hints

    def _function_name(self, function: Node | None) -> str | None:
        if function is None:
            return None
        name = function.child_by_field_name("name")
        return txt(name) if name is not None else None

    def _region(self, model: Literal) -> list[Literal]:
        """Strings around a model name: in the same function, or within a few lines when outside any function.

        Constants declared outside any function (a class field holding the system prompt) are added when
        the function itself has no instruction-style text, since that is where such prompts usually live."""
        if model.function is None:
            return [lit for lit in self.literals if abs(lit.line - model.line) <= WINDOW_LINES]
        local = [lit for lit in self.literals if lit.function == model.function]
        if any(lit.promptlike and SYSTEM_CUE.search(lit.plain) for lit in local):
            return local
        shared = [
            lit for lit in self.literals if lit.function is None and lit.promptlike and SYSTEM_CUE.search(lit.plain)
        ]
        return sorted([*local, *shared[:1]], key=lambda lit: lit.node.start_byte)

    def _roles(self, candidates: list[Literal], finding: Finding) -> tuple[Text, Text]:
        prompts = [lit for lit in candidates if lit.promptlike]
        if len(prompts) > MAX_PROMPTS:
            extra = len(prompts) - MAX_PROMPTS
            prompts = sorted(sorted(prompts, key=lambda lit: -len(lit.plain))[:MAX_PROMPTS], key=lambda lit: lit.line)
            finding.notes.append(f"{extra} other long strings nearby were not used.")
        system, user = Text(), Text()
        cued = [lit for lit in prompts if SYSTEM_CUE.search(lit.plain)]
        if len(prompts) == 1:
            (system if cued else user).add(prompts[0].text)
        elif len(prompts) == 2:
            first = cued[0] if cued else prompts[0]
            second = next(lit for lit in prompts if lit is not first)
            system.add(first.text)
            user.add(second.text)
        if prompts:
            finding.notes.append("which text is the system prompt and which the user prompt is a guess.")
        for lit in prompts:
            for problem in lit.text.problems:
                if problem not in finding.problems and "positional" not in problem:
                    finding.problems.append(f"the prompt {problem}")
        return system, user

    def run(self) -> None:
        models = [lit for lit in self.literals if MODEL_NAME.fullmatch(lit.plain.strip())]
        seen: set[tuple[int | None, str]] = set()
        for model in models:
            name = model.plain.strip()
            if AMBIGUOUS.match(name) and not self.hints:
                continue
            key = (model.function.start_byte if model.function else None, name)
            if key in seen:
                continue
            seen.add(key)
            region = self._region(model)
            finding = self._build(model.line, self._function_name(model.function), name, region)
            if finding.has_prompt:
                self.findings.append(finding)
        if not models and self.hints:
            by_function: dict[int | None, list[Literal]] = {}
            for lit in self.literals:
                by_function.setdefault(lit.function.start_byte if lit.function else None, []).append(lit)
            for lits in by_function.values():
                if any(lit.promptlike for lit in lits):
                    first = next(lit for lit in lits if lit.promptlike)
                    finding = self._build(first.line, self._function_name(first.function), None, lits)
                    if finding.has_prompt:
                        self.findings.append(finding)
        self.findings.sort(key=lambda f: f.line)

    def _build(self, line: int, function: str | None, model: str | None, region: list[Literal]) -> Finding:
        finding = Finding(self.file, line, function=function, level="broad")
        provider, name = infer_provider(model)
        if provider is None and len(self.hints) == 1:
            (provider,) = tuple(self.hints)
        finding.provider, finding.model = provider, name
        system, user = self._roles(region, finding)
        for text in (system, user):
            for variable_name in text.variables:
                if variable_name not in finding.variables:
                    finding.variables.append(variable_name)
        finding.system = system.text.strip() or None
        finding.user = user.text.strip() or None
        finding.notes.insert(0, EXTRA_NOTE)
        if model is None:
            finding.notes.append("no model name was found; set `models:` yourself.")
        finding.notes.append("settings such as temperature are not read at this level; set `params:` yourself.")
        if self.has_error:
            finding.notes.append("this file has syntax the scanner could not fully read.")
        return finding


def scan_source(source: bytes, file: str, suffix: str) -> tuple[list[Finding], list[str]]:
    scanner = Scanner(source, file, suffix)
    scanner.run()
    return scanner.findings, []


def language_name(suffix: str) -> str:
    return LANGS[suffix].name
