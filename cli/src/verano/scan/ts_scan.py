"""
Finds LLM calls in TypeScript and JavaScript with a real syntax tree (tree-sitter).

Reads what a person reading the code could: string and template literals, `+`, `.trim()`,
`[...].join("\\n")`, `dedent`, and constants declared once in the same function or at the top
of the file. Anything else is reported as "could not read", never guessed. Template `${name}`
becomes Verano's `{{ name }}`.

Recognised: OpenAI-style `chat.completions.create` and `responses.create`, Anthropic
`messages.create`, the Vercel AI SDK (`generateText`, `streamText`, `generateObject`, with
`openai("gpt-4o")`-style models), Gemini `generateContent`, any call with `model` and `messages`
in an options object, and LangChain.js prompt templates (with their `Chat*` model when there is one).
"""

import re
from collections.abc import Iterator
from typing import Any

import tree_sitter_javascript
import tree_sitter_typescript
from tree_sitter import Language, Node, Parser

from verano.scan.common import (
    LANGCHAIN_MODELS,
    MAX_DEPTH,
    PARAM_ALIASES,
    Text,
    apply_messages,
    assemble,
    escape,
    format_template,
    identifier_from,
    infer_provider,
    store_param,
    variable,
)
from verano.scan.findings import Finding

JS = Language(tree_sitter_javascript.language())
TS = Language(tree_sitter_typescript.language_typescript())
TSX = Language(tree_sitter_typescript.language_tsx())
LANGUAGES = {".js": JS, ".jsx": JS, ".mjs": JS, ".cjs": JS, ".ts": TS, ".mts": TS, ".cts": TS, ".tsx": TSX}
SUFFIXES = set(LANGUAGES)
VERCEL_PROVIDERS = {
    "openai": "openai", "anthropic": "anthropic", "google": "gemini", "groq": "groq", "mistral": "mistral",
    "xai": "xai", "togetherai": "together", "openrouter": "openrouter", "ollama": "ollama",
}  # fmt: skip
IMPORT_PROVIDERS = {
    "groq-sdk": "groq",
    "@anthropic-ai/sdk": "anthropic",
    "openai": "openai",
    "@mistralai/mistralai": "mistral",
}
WRAPPERS = {
    "parenthesized_expression",
    "await_expression",
    "as_expression",
    "satisfies_expression",
    "non_null_expression",
}
FUNCTIONS = {
    "function_declaration", "generator_function_declaration", "function_expression", "function", "arrow_function",
    "method_definition",
}  # fmt: skip
ESCAPES = {"n": "\n", "r": "\r", "t": "\t", "b": "\b", "f": "\f", "v": "\v", "0": "\0"}
ESCAPE = re.compile(r"\\(?:u\{([0-9a-fA-F]+)\}|u([0-9a-fA-F]{4})|x([0-9a-fA-F]{2})|(\r?\n)|(.))", re.S)


def txt(node: Node) -> str:
    return node.text.decode("utf-8", "replace") if node.text else ""


def unescape(raw: str) -> str:
    def one(m: re.Match[str]) -> str:
        if m.group(1):
            return chr(int(m.group(1), 16))
        if m.group(2) or m.group(3):
            return chr(int(m.group(2) or m.group(3), 16))
        if m.group(4):
            return ""
        return ESCAPES.get(m.group(5), m.group(5))

    return ESCAPE.sub(one, raw)


def walk(root: Node) -> Iterator[Node]:
    stack = [root]
    while stack:
        node = stack.pop()
        yield node
        stack.extend(reversed(node.children))


def strip(node: Node | None) -> Node | None:
    while node is not None and node.type in WRAPPERS:
        named = node.named_children
        node = named[0] if named else None
    return node


def chain(node: Node | None) -> list[str]:
    """`client.chat.completions.create` as ['client', 'chat', 'completions', 'create']."""
    node = strip(node)
    if node is None:
        return []
    if node.type == "member_expression":
        obj, prop = node.child_by_field_name("object"), node.child_by_field_name("property")
        return [*chain(obj), txt(prop)] if prop is not None else chain(obj)
    if node.type == "call_expression":
        return chain(node.child_by_field_name("function"))
    if node.type in {"identifier", "this", "super"}:
        return [txt(node)]
    return []


def object_pairs(node: Node) -> tuple[dict[str, Node], bool]:
    """The `key: value` pairs of an object literal, and whether it also spreads other options in."""
    pairs: dict[str, Node] = {}
    spread = False
    for child in node.named_children:
        if child.type == "pair":
            key, value = child.child_by_field_name("key"), child.child_by_field_name("value")
            if key is not None and value is not None:
                pairs[unescape(txt(key)[1:-1]) if key.type == "string" else txt(key)] = value
        elif child.type == "shorthand_property_identifier":
            pairs[txt(child)] = child
        elif child.type == "spread_element":
            spread = True
    return pairs, spread


def options(arguments: Node | None, first: int = 0) -> tuple[dict[str, Node], bool]:
    """The pairs of an options object passed as an argument."""
    if arguments is None or len(arguments.named_children) <= first:
        return {}, False
    node = strip(arguments.named_children[first])
    return object_pairs(node) if node is not None and node.type == "object" else ({}, False)


class Context:
    """What a name can mean at one call: declarations in the same function, at the top of the file, or an input."""

    def __init__(self, module: dict[str, Node], local: dict[str, Node], params: set[str]) -> None:
        self.module, self.local, self.params = module, local, params

    def lookup(self, name: str) -> Node | None:
        if name in self.local:
            return self.local[name]
        if name in self.params:
            return None
        return self.module.get(name)


def declarations(block: Node, before: int | None = None) -> dict[str, Node]:
    """`const name = value` statements directly inside a block or the file, before a position."""
    found: dict[str, Node] = {}
    for statement in block.named_children:
        if before is not None and statement.start_byte >= before:
            break
        if statement.type == "export_statement":
            inner = statement.child_by_field_name("declaration")
            statement = inner if inner is not None else statement
        if statement.type in {"lexical_declaration", "variable_declaration"}:
            for declarator in statement.named_children:
                name, value = declarator.child_by_field_name("name"), declarator.child_by_field_name("value")
                if (
                    declarator.type == "variable_declarator"
                    and name is not None
                    and name.type == "identifier"
                    and value
                ):
                    found[txt(name)] = value
    return found


def parameter_names(function: Node) -> set[str]:
    names: set[str] = set()
    holder = function.child_by_field_name("parameters") or function.child_by_field_name("parameter")
    if holder is None:
        return names
    for node in walk(holder):
        if node.type in {"identifier", "shorthand_property_identifier_pattern"}:
            names.add(txt(node))
    return names


def function_name(function: Node) -> str | None:
    name = function.child_by_field_name("name")
    if name is not None:
        return txt(name)
    parent = function.parent
    if parent is not None and parent.type == "variable_declarator":
        target = parent.child_by_field_name("name")
        return txt(target) if target is not None else None
    if parent is not None and parent.type == "pair":
        key = parent.child_by_field_name("key")
        return txt(key) if key is not None else None
    return None


def literal_number(node: Node | None, ctx: Context, depth: int = 0) -> Any:
    node = strip(node)
    if node is None or depth > MAX_DEPTH:
        return None
    if node.type == "number":
        text = txt(node).replace("_", "")
        try:
            return int(text) if re.fullmatch(r"\d+", text) else float(text)
        except ValueError:
            return None
    if node.type == "unary_expression" and txt(node).startswith("-"):
        inner = literal_number(node.named_children[0] if node.named_children else None, ctx, depth + 1)
        return -inner if isinstance(inner, int | float) else None
    if node.type == "identifier":
        value = ctx.lookup(txt(node))
        return literal_number(value, ctx, depth + 1) if value is not None else None
    return None


class Scanner:
    def __init__(self, source: bytes, file: str, language: Language) -> None:
        self.file = file
        self.source = source
        self.tree = Parser(language).parse(source)
        self.root = self.tree.root_node
        self.has_error = self.root.has_error
        self.module = declarations(self.root)
        self.imports = set(re.findall(r"""(?:from|require\()\s*['"]([^'"]+)['"]""", source.decode("utf-8", "replace")))
        self.findings: list[Finding] = []
        self.other: list[str] = []

    # -- reading values -----------------------------------------------------------------------------

    def context(self, node: Node) -> tuple[Context, str | None]:
        cursor = node.parent
        while cursor is not None and cursor.type not in FUNCTIONS:
            cursor = cursor.parent
        if cursor is None:
            return Context(self.module, {}, set()), None
        body = cursor.child_by_field_name("body")
        local = (
            declarations(body, before=node.start_byte) if body is not None and body.type == "statement_block" else {}
        )
        return Context(self.module, local, parameter_names(cursor)), function_name(cursor)

    def raw(self, node: Node | None, ctx: Context, depth: int = 0) -> str | None:
        """The unescaped value of fixed text, followed through constants, `+`, `.trim()` and `[...].join()`."""
        node = strip(node)
        if node is None or depth > MAX_DEPTH:
            return None
        if node.type == "string":
            return unescape(txt(node)[1:-1])
        if node.type == "template_string":
            parts: list[str] = []
            for child in node.children:
                if child.type == "string_fragment":
                    parts.append(txt(child))
                elif child.type == "escape_sequence":
                    parts.append(unescape(txt(child)))
                elif child.type == "template_substitution":
                    return None
            return "".join(parts)
        if node.type in {"identifier", "shorthand_property_identifier"}:
            value = ctx.lookup(txt(node))
            return self.raw(value, ctx, depth + 1) if value is not None else None
        if node.type == "binary_expression" and self._operator(node) == "+":
            left = self.raw(node.child_by_field_name("left"), ctx, depth + 1)
            right = self.raw(node.child_by_field_name("right"), ctx, depth + 1)
            return left + right if left is not None and right is not None else None
        if node.type == "call_expression":
            return self._raw_call(node, ctx, depth)
        return None

    @staticmethod
    def _operator(node: Node) -> str:
        op = node.child_by_field_name("operator")
        return txt(op) if op is not None else ""

    def _raw_call(self, node: Node, ctx: Context, depth: int) -> str | None:
        fn = node.child_by_field_name("function")
        args = node.child_by_field_name("arguments")
        if fn is None:
            return None
        if fn.type == "member_expression":
            prop, obj = fn.child_by_field_name("property"), fn.child_by_field_name("object")
            name = txt(prop) if prop is not None else ""
            if name in {"trim", "trimStart", "trimEnd"} and (args is None or not args.named_children):
                inner = self.raw(obj, ctx, depth + 1)
                return None if inner is None else inner.strip()
            if name == "join" and obj is not None and strip(obj) is not None and strip(obj).type == "array":  # type: ignore[union-attr]
                return self._joined(strip(obj), args, ctx, depth)
        if (
            fn.type == "identifier"
            and txt(fn) in {"dedent", "stripIndent", "oneLine", "stripIndents"}
            and args is not None
        ):
            named = args.named_children
            return self.raw(named[0], ctx, depth + 1) if named else None
        return None

    def _joined(self, array: Node | None, args: Node | None, ctx: Context, depth: int) -> str | None:
        separator = (
            self.raw(args.named_children[0], ctx, depth + 1) if args is not None and args.named_children else ","
        )
        items = [self.raw(e, ctx, depth + 1) for e in array.named_children] if array is not None else []
        return (
            separator.join(i for i in items if i is not None) if separator is not None and None not in items else None
        )

    def convert(self, node: Node | None, ctx: Context, depth: int = 0) -> Text:
        """A string expression as a Verano template; `problems` says what could not be read."""
        node = strip(node)
        if node is None:
            return Text(problems=["is missing"])
        if depth > MAX_DEPTH:
            return Text(problems=["is built from too many nested pieces"])
        fixed = self.raw(node, ctx)
        if fixed is not None and node.type != "identifier":
            return Text(escape(fixed))
        if node.type == "template_string":
            return self._template(node, ctx, depth)
        if node.type == "binary_expression" and self._operator(node) == "+":
            out = Text()
            out.add(self.convert(node.child_by_field_name("left"), ctx, depth + 1))
            out.add(self.convert(node.child_by_field_name("right"), ctx, depth + 1))
            return out
        if node.type in {"identifier", "shorthand_property_identifier"}:
            name = txt(node)
            value = ctx.lookup(name)
            if value is not None:
                resolved = self.convert(value, ctx, depth + 1)
                if not resolved.problems or resolved.text:
                    return resolved
            return variable(name)
        if node.type in {"member_expression", "subscript_expression"}:
            source = txt(node)
            name = identifier_from(source)
            return Text(variable(name).text, [name], [f"uses the expression `{source[:50]}`"])
        if node.type == "call_expression":
            fn = node.child_by_field_name("function")
            return Text(problems=[f"is built by calling `{txt(fn)[:40] if fn is not None else '?'}(…)`"])
        return Text(problems=[f"is built with `{txt(node)[:50]}`"])

    def _template(self, node: Node, ctx: Context, depth: int) -> Text:
        out = Text()
        for child in node.children:
            if child.type == "string_fragment":
                out.text += escape(txt(child))
            elif child.type == "escape_sequence":
                out.text += escape(unescape(txt(child)))
            elif child.type == "template_substitution":
                inner = strip(child.named_children[0] if child.named_children else None)
                if inner is not None and inner.type == "identifier":
                    out.add(self.convert(inner, ctx, depth + 1))
                else:
                    source = txt(inner) if inner is not None else ""
                    name = identifier_from(source)
                    out.add(Text(variable(name).text, [name], [f"uses the expression `${{{source[:50]}}}`"]))
        return out

    def read_params(self, pairs: dict[str, Node], ctx: Context, finding: Finding) -> None:
        for key, node in pairs.items():
            if key not in PARAM_ALIASES:
                continue
            target = PARAM_ALIASES[key]
            value: Any
            if target == "stop":
                value = self.raw(node, ctx)
                inner = strip(node)
                if value is None and inner is not None and inner.type == "array":
                    items = [self.raw(e, ctx) for e in inner.named_children]
                    value = items if None not in items else None
            else:
                value = literal_number(node, ctx)
            store_param(finding, key, value, txt(node))

    # -- messages -------------------------------------------------------------------------------------

    def role_messages(self, node: Node | None, ctx: Context, finding: Finding) -> list[tuple[str, Text]] | None:
        node = strip(node)
        if node is not None and node.type in {"identifier", "shorthand_property_identifier"}:
            value = ctx.lookup(txt(node))
            if value is None:
                finding.problems.append(f"the messages come from `{txt(node)}`, which is passed in from elsewhere")
                return None
            node = strip(value)
        if node is None or node.type != "array":
            finding.problems.append("the messages are built dynamically")
            return None
        messages: list[tuple[str, Text]] = []
        for element in node.named_children:
            element = strip(element)  # type: ignore[assignment]
            if element is None or element.type != "object":
                finding.problems.append("a message is not written as { role, content }")
                return None
            pairs, spread = object_pairs(element)
            role = self.raw(pairs["role"], ctx) if "role" in pairs else None
            if spread or role is None or "content" not in pairs:
                finding.problems.append("a message has no readable role or content")
                return None
            messages.append((role, self.convert(pairs["content"], ctx)))
        return messages

    # -- calls ----------------------------------------------------------------------------------------

    def run(self) -> None:
        constructors: list[tuple[Node, str]] = []
        for node in walk(self.root):
            if node.type == "new_expression":
                ctor = node.child_by_field_name("constructor")
                name = (chain(ctor) or [""])[-1]
                if name in LANGCHAIN_MODELS:
                    constructors.append((node, LANGCHAIN_MODELS[name]))
                if name.endswith("TextSplitter"):
                    self.other.append(f"{self.file}:{node.start_point[0] + 1}: a text splitter (chunking)")
        for node in walk(self.root):
            if node.type != "call_expression":
                continue
            parts = chain(node.child_by_field_name("function"))
            if not parts:
                continue
            self._other(node, parts)
            finding = self._model_call(node, parts) or self._langchain_prompt(node, parts, constructors)
            if finding is not None:
                if self.has_error:
                    finding.notes.append("this file has syntax the scanner could not fully read; check this prompt.")
                self.findings.append(finding)
        self.findings.sort(key=lambda f: f.line)

    def _other(self, node: Node, parts: list[str]) -> None:
        last, label = parts[-1], None
        if ("embeddings" in parts and last == "create") or last in {"embed", "embedMany", "OpenAIEmbeddings"}:
            label = "an embedding model"
        elif last in {"similaritySearch", "asRetriever", "similaritySearchWithScore"}:
            label = "document retrieval"
        if label:
            self.other.append(f"{self.file}:{node.start_point[0] + 1}: {label}")

    def _vercel_model(self, node: Node | None, ctx: Context) -> tuple[str | None, str | None]:
        """(provider, model) of `openai("gpt-4o")`, `openai.chat("gpt-4o")` or a plain model string."""
        node = strip(node)
        if node is not None and node.type == "call_expression":
            parts = chain(node.child_by_field_name("function"))
            args = node.child_by_field_name("arguments")
            if parts and parts[0] in VERCEL_PROVIDERS and args is not None and args.named_children:
                return VERCEL_PROVIDERS[parts[0]], self.raw(args.named_children[0], ctx)
        if node is not None:
            return None, self.raw(node, ctx)
        return None, None

    def _model_call(self, node: Node, parts: list[str]) -> Finding | None:
        last = parts[-1]
        args = node.child_by_field_name("arguments")
        pairs, spread = options(args)
        default: str | None
        vercel = last in {"generateText", "streamText", "generateObject", "streamObject"}
        if "completions" in parts and "chat" in parts and last in {"create", "parse", "stream"}:
            default = next((p for i, p in IMPORT_PROVIDERS.items() if i in self.imports and p != "openai"), "openai")
        elif "responses" in parts and last in {"create", "parse", "stream"}:
            default = "openai"
        elif "messages" in parts and last in {"create", "stream"}:
            default = "anthropic"
        elif vercel:
            default = None
        elif last in {"generateContent", "generateContentStream"}:
            default = "gemini"
        elif "model" in pairs and "messages" in pairs:
            default = None
        else:
            return None
        ctx, function = self.context(node)
        finding = Finding(self.file, node.start_point[0] + 1, function=function)
        provider: str | None = None
        model: str | None
        if vercel:
            provider, model = self._vercel_model(pairs.get("model"), ctx)
        else:
            model = self.raw(pairs["model"], ctx) if "model" in pairs else None
        if model is None and default == "gemini":
            model = self._gemini_model(ctx)
        if model is None:
            finding.notes.append("the model is not a fixed value" if "model" in pairs else "no model found")
        guessed, name = infer_provider(model)
        finding.provider, finding.model = provider or guessed or default, name
        self.read_params(pairs, ctx, finding)
        if spread:
            finding.problems.append("the call spreads other options in (...options), which can't be read")
        self._prompt_of_call(node, pairs, ctx, finding, last)
        for key in ("tools", "functions", "toolChoice", "tool_choice"):
            if key in pairs:
                finding.notes.append(f"it uses {key}; Verano can't test tool use yet.")
                self.other.append(f"{self.file}:{finding.line}: {key} (tool use)")
        if "response_format" in pairs or "schema" in pairs:
            finding.notes.append("it asks for a structured response format; copy that into `task.output_schema`.")
        return finding

    def _gemini_model(self, ctx: Context) -> str | None:
        for node in walk(self.root):
            if node.type == "call_expression" and chain(node.child_by_field_name("function"))[-1:] == [
                "getGenerativeModel"
            ]:
                pairs, _ = options(node.child_by_field_name("arguments"))
                if "model" in pairs:
                    return self.raw(pairs["model"], ctx)
        return None

    def _prompt_of_call(self, node: Node, pairs: dict[str, Node], ctx: Context, finding: Finding, last: str) -> None:
        system, user, found = Text(), Text(), False
        for key in ("system", "instructions", "systemInstruction"):
            if key in pairs:
                system, found = self.convert(pairs[key], ctx), True
        if "messages" in pairs:
            messages = self.role_messages(pairs["messages"], ctx, finding)
            if messages is None:
                return
            apply_messages(messages, finding)
            if system.text:
                finding.system = (system.text.strip() + ("\n\n" + finding.system if finding.system else "")) or None
                for name in system.variables:
                    if name not in finding.variables:
                        finding.variables.append(name)
            return
        content = pairs.get("prompt") or pairs.get("input") or pairs.get("contents")
        if content is None and last.startswith("generateContent"):
            args = node.child_by_field_name("arguments")
            content = args.named_children[0] if args is not None and args.named_children else None
            if content is not None and strip(content) is not None and strip(content).type == "object":  # type: ignore[union-attr]
                content = None
        if content is not None:
            user, found = self.convert(content, ctx), True
        if not found:
            finding.problems.append("no prompt text found in this call")
            return
        assemble(finding, system, user)

    def _langchain_prompt(self, node: Node, parts: list[str], constructors: list[tuple[Node, str]]) -> Finding | None:
        last = parts[-1]
        if last not in {"fromMessages", "fromTemplate"} or not any(p.endswith("Template") for p in parts):
            return None
        ctx, function = self.context(node)
        finding = Finding(self.file, node.start_point[0] + 1, kind="prompt", function=function)
        args = node.child_by_field_name("arguments")
        first = strip(args.named_children[0]) if args is not None and args.named_children else None
        system, user = Text(), Text()
        if last == "fromTemplate" and first is not None:
            raw = self.raw(first, ctx)
            if raw is None:
                finding.problems.append("the template is not fixed text")
            else:
                user = format_template(raw)
        elif first is not None and first.type == "array":
            for element in first.named_children:
                element = strip(element)  # type: ignore[assignment]
                items = element.named_children if element is not None and element.type == "array" else []
                if len(items) != 2:
                    finding.problems.append("a message of the template is not written as [role, text]")
                    continue
                role, raw = self.raw(items[0], ctx), self.raw(items[1], ctx)
                if role is None or raw is None:
                    finding.problems.append("a message of the template is not fixed text")
                elif role in {"system", "developer"}:
                    system.add(format_template(raw))
                elif role in {"human", "user"}:
                    user = format_template(raw)
        else:
            finding.problems.append("the template is not written as a list of [role, text]")
        assemble(finding, system, user)
        if len(constructors) == 1:
            call, provider = constructors[0]
            pairs, _ = options(call.child_by_field_name("arguments"))
            model_node = pairs.get("model") or pairs.get("modelName")
            model = self.raw(model_node, ctx) if model_node is not None else None
            guessed, name = infer_provider(model)
            finding.provider, finding.model = guessed or provider, name
            self.read_params(pairs, ctx, finding)
        else:
            finding.notes.append("no single model is created next to this template; set `models:` yourself.")
        return finding


def scan_source(source: bytes, file: str, suffix: str) -> tuple[list[Finding], list[str]]:
    scanner = Scanner(source, file, LANGUAGES[suffix])
    scanner.run()
    return scanner.findings, scanner.other
