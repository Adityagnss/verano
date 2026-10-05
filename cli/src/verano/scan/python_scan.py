"""
Finds LLM calls in Python with the syntax tree (`ast`): which model, which settings, which prompt.

It follows what a reader of the code could follow: string constants, f-strings, `"...".format()`,
concatenation, `dedent` / `strip`, and names assigned once in the same function or at the top of
the file. A value that depends on a function call, an attribute or anything else is reported as
"could not read", never guessed. Prompt variables become Verano's `{{ name }}`.

Recognised: the OpenAI-style `chat.completions.create` and `responses.create`, Anthropic
`messages.create`, `litellm.completion`, Gemini `generate_content`, any call that passes `model`
with a `messages` list, and LangChain prompt templates (with their `Chat*` model when there is one).
"""

import ast
import inspect
import textwrap
from pathlib import Path
from typing import Any

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

IMPORT_PROVIDERS = {"groq": "groq", "anthropic": "anthropic", "openai": "openai", "mistralai": "mistral"}


def _expression(node: ast.AST) -> str:
    return identifier_from(ast.unparse(node))


class Context:
    """What a name can mean at one call: assignments in the same function, at the top of the file, or an input."""

    def __init__(self, module: dict[str, ast.expr], local: dict[str, ast.expr], params: set[str]) -> None:
        self.module, self.local, self.params = module, local, params

    def lookup(self, name: str) -> ast.expr | None:
        if name in self.local:
            return self.local[name]
        if name in self.params:
            return None
        return self.module.get(name)


def _assignments(body: list[ast.stmt], before: int | None = None) -> dict[str, ast.expr]:
    found: dict[str, ast.expr] = {}
    for stmt in body:
        if before is not None and stmt.lineno >= before:
            break
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
            found[stmt.targets[0].id] = stmt.value
        elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name) and stmt.value is not None:
            found[stmt.target.id] = stmt.value
    return found


def convert(node: ast.AST, ctx: Context, depth: int = 0) -> Text:
    """A string expression as a Verano template; `problems` says what could not be read."""
    if depth > MAX_DEPTH:
        return Text(problems=["is built from too many nested pieces"])
    if isinstance(node, ast.Constant):
        return Text(escape(node.value)) if isinstance(node.value, str) else Text(problems=["is not text"])
    if isinstance(node, ast.JoinedStr):
        return _fstring(node, ctx, depth)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        out = Text()
        out.add(convert(node.left, ctx, depth + 1))
        out.add(convert(node.right, ctx, depth + 1))
        return out
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
        out = convert(node.left, ctx, depth + 1)
        out.problems.append("uses %-style formatting")
        return out
    if isinstance(node, ast.Name):
        return _name(node, ctx, depth)
    if isinstance(node, ast.Call):
        return _call(node, ctx, depth)
    if isinstance(node, ast.Attribute | ast.Subscript):
        name = _expression(node)
        return Text(variable(name).text, [name], [f"uses the expression `{ast.unparse(node)[:50]}`"])
    return Text(problems=[f"is built with `{ast.unparse(node)[:50]}`"])


def _fstring(node: ast.JoinedStr, ctx: Context, depth: int) -> Text:
    out = Text()
    for part in node.values:
        if isinstance(part, ast.Constant):
            out.text += escape(str(part.value))
        elif isinstance(part, ast.FormattedValue):
            value = part.value
            if isinstance(value, ast.Name):
                out.add(_name(value, ctx, depth))
            else:
                name = _expression(value)
                out.add(Text(variable(name).text, [name], [f"uses the expression `{{{ast.unparse(value)[:50]}}}`"]))
    return out


def _name(node: ast.Name, ctx: Context, depth: int) -> Text:
    value = ctx.lookup(node.id)
    if value is not None:
        resolved = convert(value, ctx, depth + 1)
        if not resolved.problems or resolved.text:
            return resolved
    return variable(node.id)


UNWRAP = {"dedent", "cleandoc", "strip", "lstrip", "rstrip", "format_map"}


def _call(node: ast.Call, ctx: Context, depth: int) -> Text:
    func = node.func
    called = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else None
    if called == "format" and isinstance(func, ast.Attribute):
        raw = _raw(func.value, ctx)
        if raw is None:
            return Text(problems=["is a `.format()` on something that is not fixed text"])
        return format_template(raw)
    if called in UNWRAP:
        raw = _raw(node, ctx)
        if raw is not None:
            return Text(escape(raw))
        inner = func.value if isinstance(func, ast.Attribute) else (node.args[0] if node.args else None)
        if inner is not None:
            return convert(inner, ctx, depth + 1)
    return Text(problems=[f"is built by calling `{ast.unparse(func)[:40]}(…)`"])


def _raw(node: ast.AST, ctx: Context, depth: int = 0) -> str | None:
    """The unescaped value of a string constant, followed through names and `dedent` / `strip`."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name) and depth < MAX_DEPTH:
        value = ctx.lookup(node.id)
        return _raw(value, ctx, depth + 1) if value is not None else None
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _raw(node.left, ctx, depth + 1), _raw(node.right, ctx, depth + 1)
        return left + right if left is not None and right is not None else None
    if isinstance(node, ast.Call) and depth < MAX_DEPTH:
        return _raw_wrapped(node, ctx, depth)
    return None


def _raw_wrapped(node: ast.Call, ctx: Context, depth: int) -> str | None:
    func = node.func
    called = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else None
    if called in {"dedent", "cleandoc"} and node.args:
        inner = _raw(node.args[0], ctx, depth + 1)
        return None if inner is None else (textwrap.dedent(inner) if called == "dedent" else inspect.cleandoc(inner))
    if called in {"strip", "lstrip", "rstrip"} and isinstance(func, ast.Attribute) and not node.args:
        inner = _raw(func.value, ctx, depth + 1)
        return None if inner is None else getattr(inner, called)()
    return None


# -- calls -----------------------------------------------------------------------------------------


def chain(node: ast.AST) -> list[str]:
    """`client.chat.completions.create` as ['client', 'chat', 'completions', 'create']."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    elif isinstance(node, ast.Call):
        parts.extend(reversed(chain(node.func)))
    return list(reversed(parts))


def _literal(node: ast.AST, ctx: Context, depth: int = 0) -> Any:
    if isinstance(node, ast.Name) and depth < MAX_DEPTH:
        value = ctx.lookup(node.id)
        return _literal(value, ctx, depth + 1) if value is not None else None
    raw = _raw(node, ctx)
    if raw is not None:
        return raw
    if isinstance(node, ast.Constant) and isinstance(node.value, int | float) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub) and isinstance(node.operand, ast.Constant):
        return -node.operand.value if isinstance(node.operand.value, int | float) else None
    if isinstance(node, ast.List | ast.Tuple):
        items = [_literal(e, ctx) for e in node.elts]
        return items if all(isinstance(i, str) for i in items) else None
    return None


def read_params(keywords: dict[str, ast.expr], ctx: Context, finding: Finding) -> None:
    for key, node in keywords.items():
        if key in PARAM_ALIASES:
            store_param(finding, key, _literal(node, ctx), ast.unparse(node))


def _role_messages(node: ast.AST, ctx: Context, finding: Finding) -> list[tuple[str, Text]] | None:
    """(role, text) for each message of a literal list of {"role": ..., "content": ...}."""
    if isinstance(node, ast.Name):
        value = ctx.lookup(node.id)
        if value is None:
            finding.problems.append(f"the messages come from `{node.id}`, which is passed in from elsewhere")
            return None
        node = value
    if not isinstance(node, ast.List):
        finding.problems.append("the messages are built dynamically")
        return None
    messages: list[tuple[str, Text]] = []
    for element in node.elts:
        if not isinstance(element, ast.Dict):
            finding.problems.append("a message is not written as {role, content}")
            return None
        pairs = {k.value: v for k, v in zip(element.keys, element.values, strict=True) if isinstance(k, ast.Constant)}
        role = _raw(pairs["role"], ctx) if "role" in pairs else None
        if role is None or "content" not in pairs:
            finding.problems.append("a message has no readable role or content")
            return None
        messages.append((role, convert(pairs["content"], ctx)))
    return messages


def _content_text(node: ast.AST, ctx: Context) -> Text:
    """A `system=` value: text, or Anthropic's list of {"type": "text", "text": ...} blocks."""
    if isinstance(node, ast.List):
        out = Text()
        for block in node.elts:
            if isinstance(block, ast.Dict):
                pairs = {
                    k.value: v for k, v in zip(block.keys, block.values, strict=True) if isinstance(k, ast.Constant)
                }
                if "text" in pairs:
                    if out.text:
                        out.text += "\n\n"
                    out.add(convert(pairs["text"], ctx))
        return out
    return convert(node, ctx)


class Scanner:
    def __init__(self, source: str, file: str) -> None:
        self.file = file
        self.tree = ast.parse(source)
        self.parents: dict[ast.AST, ast.AST] = {}
        for parent in ast.walk(self.tree):
            for child in ast.iter_child_nodes(parent):
                self.parents[child] = parent
        self.module = _assignments(self.tree.body)
        self.imports = {
            (n.module or "").split(".")[0] if isinstance(n, ast.ImportFrom) else a.name.split(".")[0]
            for n in ast.walk(self.tree)
            if isinstance(n, ast.Import | ast.ImportFrom)
            for a in (n.names if isinstance(n, ast.Import) else [ast.alias(name="")])
        }
        self.findings: list[Finding] = []
        self.other: list[str] = []

    def function_of(self, node: ast.AST) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
        cursor = self.parents.get(node)
        while cursor is not None:
            if isinstance(cursor, ast.FunctionDef | ast.AsyncFunctionDef):
                return cursor
            cursor = self.parents.get(cursor)
        return None

    def context(self, node: ast.AST) -> tuple[Context, str | None]:
        function = self.function_of(node)
        if function is None:
            return Context(self.module, {}, set()), None
        args = function.args
        params = {a.arg for a in [*args.posonlyargs, *args.args, *args.kwonlyargs]}
        local = _assignments(function.body, before=getattr(node, "lineno", None))
        return Context(self.module, local, params), function.name

    def run(self) -> None:
        constructors = self._constructors()
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.Call):
                continue
            parts = chain(node.func)
            if not parts:
                continue
            self._other(node, parts)
            finding = self._model_call(node, parts) or self._langchain_prompt(node, parts, constructors)
            if finding is not None:
                self.findings.append(finding)
        self.findings.sort(key=lambda f: f.line)

    def _constructors(self) -> list[tuple[ast.Call, str]]:
        found = []
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Call):
                name = chain(node.func)[-1:] or [""]
                if name[0] in LANGCHAIN_MODELS:
                    found.append((node, LANGCHAIN_MODELS[name[0]]))
        return found

    def _other(self, node: ast.Call, parts: list[str]) -> None:
        last = parts[-1]
        label = None
        if ("embeddings" in parts and last == "create") or last in {"OpenAIEmbeddings", "SentenceTransformer"}:
            label = "an embedding model"
        elif last.endswith("TextSplitter"):
            label = "a text splitter (chunking)"
        elif last in {"similarity_search", "as_retriever", "similarity_search_with_score"}:
            label = "document retrieval"
        if label:
            self.other.append(f"{self.file}:{node.lineno}: {label}")

    def _provider(self, model: str | None, default: str | None) -> tuple[str | None, str | None]:
        provider, name = infer_provider(model)
        if provider is None:
            provider = default
        return provider, name

    def _model_call(self, node: ast.Call, parts: list[str]) -> Finding | None:
        keywords = {k.arg: k.value for k in node.keywords if k.arg}
        last = parts[-1]
        default: str | None
        if "completions" in parts and "chat" in parts and last in {"create", "acreate", "parse"}:
            default = next((p for i, p in IMPORT_PROVIDERS.items() if i in self.imports and i != "openai"), "openai")
        elif "responses" in parts and last in {"create", "parse"}:
            default = "openai"
        elif "messages" in parts and last in {"create", "stream", "acreate"}:
            default = "anthropic"
        elif last in {"completion", "acompletion"} and ("litellm" in parts or "litellm" in self.imports):
            default = None
        elif last in {"generate_content", "generate_content_async"}:
            default = "gemini"
        elif "model" in keywords and "messages" in keywords:
            default = None
        else:
            return None
        ctx, function = self.context(node)
        finding = Finding(self.file, node.lineno, function=function)
        model_node = keywords.get("model")
        model = _raw(model_node, ctx) if model_node is not None else None
        if model is None and default == "gemini":
            model = self._gemini_model()
        if model is None:
            finding.notes.append("the model is not a fixed value" if model_node is not None else "no model found")
        finding.provider, finding.model = self._provider(model, default)
        read_params(keywords, ctx, finding)
        if any(k.arg is None for k in node.keywords):
            finding.problems.append("the call passes **options, which can't be read")
        self._prompt_of_call(node, keywords, ctx, finding, last)
        for name in ("tools", "functions", "tool_choice"):
            if name in keywords:
                finding.notes.append(f"it uses {name}; Verano can't test tool use yet.")
                self.other.append(f"{self.file}:{node.lineno}: {name} (tool use)")
        if "response_format" in keywords:
            finding.notes.append("it asks for a structured response format; copy that into `task.output_schema`.")
        return finding

    def _gemini_model(self) -> str | None:
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Call) and chain(node.func)[-1:] == ["GenerativeModel"] and node.args:
                ctx = Context(self.module, {}, set())
                return _raw(node.args[0], ctx)
        return None

    def _prompt_of_call(
        self, node: ast.Call, keywords: dict[str, ast.expr], ctx: Context, finding: Finding, last: str
    ) -> None:
        system = Text()
        user = Text()
        found = False
        for key in ("system", "instructions"):
            if key in keywords:
                system = _content_text(keywords[key], ctx)
                found = True
        if "messages" in keywords:
            messages = _role_messages(keywords["messages"], ctx, finding)
            if messages is None:
                return
            apply_messages(messages, finding)
            if system.text:
                finding.system = (system.text.strip() + ("\n\n" + finding.system if finding.system else "")) or None
                for name in system.variables:
                    if name not in finding.variables:
                        finding.variables.append(name)
            return
        content = keywords.get("input") or keywords.get("prompt") or keywords.get("contents")
        if content is None and last.startswith("generate_content") and node.args:
            content = node.args[0]
        if content is not None:
            user = convert(content, ctx)
            found = True
        if not found:
            finding.problems.append("no prompt text found in this call")
            return
        assemble(finding, system, user)

    def _langchain_prompt(
        self, node: ast.Call, parts: list[str], constructors: list[tuple[ast.Call, str]]
    ) -> Finding | None:
        last = parts[-1]
        if last not in {"from_messages", "from_template"} or not any("Template" in p for p in parts):
            return None
        ctx, function = self.context(node)
        finding = Finding(self.file, node.lineno, kind="prompt", function=function)
        system, user = Text(), Text()
        if last == "from_template" and node.args:
            raw = _raw(node.args[0], ctx)
            if raw is None:
                finding.problems.append("the template is not fixed text")
            else:
                user = format_template(raw)
        elif node.args and isinstance(node.args[0], ast.List):
            for element in node.args[0].elts:
                if isinstance(element, ast.Tuple) and len(element.elts) == 2:
                    role, raw = _raw(element.elts[0], ctx), _raw(element.elts[1], ctx)
                    if role is None or raw is None:
                        finding.problems.append("a message of the template is not fixed text")
                        continue
                    text = format_template(raw)
                    if role in {"system", "developer"}:
                        system.add(text)
                    elif role in {"human", "user"}:
                        user = text
        else:
            finding.problems.append("the template is not written as a list of (role, text)")
        assemble(finding, system, user)
        if len(constructors) == 1:
            call, provider = constructors[0]
            keywords = {k.arg: k.value for k in call.keywords if k.arg}
            model_node = keywords.get("model") or keywords.get("model_name")
            model = _raw(model_node, ctx) if model_node is not None else None
            finding.provider, finding.model = self._provider(model, provider)
            read_params(keywords, ctx, finding)
        else:
            finding.notes.append("no single model is created next to this template; set `models:` yourself.")
        return finding


def scan_source(source: str, file: str) -> tuple[list[Finding], list[str]]:
    """The findings and other notes of one Python file. Raises SyntaxError for code Python can't parse."""
    scanner = Scanner(source, file)
    scanner.run()
    return scanner.findings, scanner.other


def read_python(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8-sig")
    except (UnicodeDecodeError, OSError):
        return None
