"""
Java prompts read from the message calls of Spring AI and LangChain4j (finding F3, check 5.10).

These libraries keep the model in configuration, so a Java file using them often names no model
and no provider, and the clue-based Broad scan finds nothing in it. The prompt is still written
at a call this module can read: `ChatClient` chains (`defaultSystem(...)`, `.system(...)`,
`.user(...)`) and message objects (`new SystemMessage(...)`, `UserMessage.from(...)`).

An argument is read when it is a string, a `static final` string constant of the same file, or a
`+` join of those with other values; each other value becomes a `{{ variable }}`. An argument
that only exists at run time (a field, a parameter, a method's result) is never guessed: the role
is left empty and the finding says why, because a wrong prompt text is worse than a missing one.
Calls are grouped by class, one finding per class.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from tree_sitter import Node

from verano.scan.common import Text, identifier_from, variable

LIBRARIES = ("org.springframework.ai", "dev.langchain4j")
ROLE_METHODS = {"system": "system", "defaultSystem": "system", "user": "user", "defaultUser": "user"}
ROLE_TYPES = {"SystemMessage": "system", "UserMessage": "user"}
CALL_NOTE = (
    "read from a Spring AI / LangChain4j message call; the model is set in configuration, so set `models:` yourself."
)


@dataclass
class RoleCall:
    role: str
    line: int
    method: str | None
    text: Text | None  # None: the text only exists at run time
    source: str


@dataclass
class ClassCalls:
    name: str
    calls: list[RoleCall] = field(default_factory=list)


def _txt(node: Node | None) -> str:
    return node.text.decode("utf-8", "replace") if node is not None and node.text else ""


def uses_library(source: bytes) -> bool:
    text = source.decode("utf-8", "replace")
    return any(name in text for name in LIBRARIES)


class JavaCalls:
    def __init__(self, root: Node, read_string: Callable[[Node], Text]) -> None:
        self.root = root
        self.read_string = read_string
        self.constants = self._constants()

    def _constants(self) -> dict[str, Node]:
        """`static final` fields holding a string (or a join of strings), by name."""
        found: dict[str, Node] = {}
        for node in _walk(self.root):
            if node.type != "field_declaration":
                continue
            modifiers = next((c for c in node.children if c.type == "modifiers"), None)
            words = _txt(modifiers).split()
            if "static" not in words or "final" not in words:
                continue
            for declarator in (c for c in node.children if c.type == "variable_declarator"):
                name, value = declarator.child_by_field_name("name"), declarator.child_by_field_name("value")
                if name is not None and value is not None:
                    found[_txt(name)] = value
        return found

    def read(self, node: Node, depth: int = 0) -> Text | None:
        """The argument as a template, or None when its text only exists at run time."""
        if node.type == "string_literal":
            return self.read_string(node)
        if node.type == "parenthesized_expression" and node.named_child_count == 1:
            inner = node.named_children[0]
            return self.read(inner, depth)
        if node.type == "identifier":
            value = self.constants.get(_txt(node))
            return self.read(value, depth + 1) if value is not None and depth < 5 else None
        if node.type == "binary_expression" and _txt(node.child_by_field_name("operator")) == "+":
            text = Text()
            for side in (node.child_by_field_name("left"), node.child_by_field_name("right")):
                if side is None:
                    return None
                part = self.read(side, depth)
                if part is None:
                    name = _txt(side) if side.type == "identifier" else identifier_from(_txt(side))
                    if side.type != "identifier":
                        text.problems.append(f"uses the expression `{_txt(side)[:50]}`")
                    part = variable(name)
                text.add(part)
            return text if text.text.replace("{{", "").strip() else None
        return None

    def classes(self) -> list[ClassCalls]:
        by_class: dict[int, ClassCalls] = {}
        for node in _walk(self.root):
            role, argument = _role_and_argument(node)
            if role is None or argument is None:
                continue
            owner = _enclosing(node, {"class_declaration", "record_declaration", "enum_declaration"})
            key = owner.start_byte if owner is not None else -1
            name = _txt(owner.child_by_field_name("name")) if owner is not None else "file"
            calls = by_class.setdefault(key, ClassCalls(name))
            method = _enclosing(node, {"method_declaration", "constructor_declaration"})
            calls.calls.append(
                RoleCall(
                    role,
                    node.start_point[0] + 1,
                    _txt(method.child_by_field_name("name")) if method is not None else None,
                    self.read(argument),
                    _txt(argument),
                )
            )
        return list(by_class.values())


def _walk(root: Node) -> list[Node]:
    out, stack = [], [root]
    while stack:
        node = stack.pop()
        out.append(node)
        stack.extend(reversed(node.children))
    return out


def _enclosing(node: Node, types: set[str]) -> Node | None:
    cursor = node.parent
    while cursor is not None and cursor.type not in types:
        cursor = cursor.parent
    return cursor


def _single_argument(arguments: Node | None) -> Node | None:
    if arguments is None or arguments.named_child_count != 1:
        return None
    return arguments.named_children[0]


def _role_and_argument(node: Node) -> tuple[str | None, Node | None]:
    if node.type == "object_creation_expression":
        role = ROLE_TYPES.get(_txt(node.child_by_field_name("type")).split("<")[0].split(".")[-1])
        return role, _single_argument(node.child_by_field_name("arguments")) if role else None
    if node.type == "method_invocation":
        name = _txt(node.child_by_field_name("name"))
        receiver = _txt(node.child_by_field_name("object")).split(".")[-1]
        if name == "from" and receiver in ROLE_TYPES:
            return ROLE_TYPES[receiver], _single_argument(node.child_by_field_name("arguments"))
        if name in ROLE_METHODS and node.child_by_field_name("object") is not None:
            return ROLE_METHODS[name], _single_argument(node.child_by_field_name("arguments"))
    return None, None


def pick(calls: list[RoleCall], role: str) -> tuple[Text, list[str]]:
    """The one text for a role, and why there is none when it can't be told."""
    mine = [call for call in calls if call.role == role]
    if not mine:
        return Text(), []
    runtime = [call for call in mine if call.text is None]
    texts = {call.text.text: call.text for call in mine if call.text is not None}
    if runtime:
        names = ", ".join(f"`{call.source[:40]}`" for call in runtime[:3])
        return Text(), [f"the {role} prompt is built at run time ({names}); copy it in yourself"]
    if len(texts) > 1:
        return Text(), [f"{len(texts)} different {role} prompts are sent here; keep the one you want to test"]
    return next(iter(texts.values())), []
