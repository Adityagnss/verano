"""
Reads and checks a `verano.yaml`, and finds the files it points to.

Every problem is reported together, each with the file, the line and the prompt it is about, so
one run of `verano validate` is enough to fix a file. Prompt files, the golden file and the
input files must live inside the folder of the YAML (the repository): a config file read from
a pull request must not be able to make the CLI upload `~/.ssh/id_rsa`.
"""

import difflib
import glob
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from verano import cases as case_tables
from verano.errors import CliError
from verano.spec import PromptEntry, VeranoFile, variables_of

FILENAME = "verano.yaml"
MAX_YAML_BYTES = 1_000_000
MAX_PROMPT_BYTES = 200_000
MAX_INPUT_FILES = 1000
GOLDEN_SUFFIXES = {".csv", ".xlsx", ".json", ".jsonl"}
SEPARATOR = " · "


@dataclass(frozen=True)
class Problem:
    line: int | None
    where: str
    message: str


class SpecError(CliError):
    """The file has problems. `problems` lists them all; the message shows each on a line."""

    def __init__(self, path: Path, problems: list[Problem]) -> None:
        self.problems = problems
        lines = [
            f"{path.name}{f':{p.line}' if p.line else ''}: {p.where + ': ' if p.where else ''}{p.message}"
            for p in problems
        ]
        noun = "problem" if len(problems) == 1 else "problems"
        super().__init__(f"{path.name} has {len(problems)} {noun}:\n  " + "\n  ".join(lines))


@dataclass(frozen=True)
class ResolvedPrompt:
    entry: PromptEntry
    project_name: str
    system: str | None
    user: str | None
    golden: Path | None
    inputs: list[Path]
    line: int | None = None
    cases: case_tables.Built | None = None

    @property
    def variables(self) -> list[str]:
        return variables_of(self.system, self.user)


@dataclass(frozen=True)
class Loaded:
    path: Path
    root: Path
    file: VeranoFile
    prompts: list[ResolvedPrompt]
    warnings: list[str] = field(default_factory=list)


class _Loader(yaml.SafeLoader):
    pass


def _no_duplicates(loader: _Loader, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
    seen: set[Any] = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in seen:
            raise yaml.constructor.ConstructorError(None, None, f"'{key}' is written twice here", key_node.start_mark)
        seen.add(key)
    return loader.construct_mapping(node, deep=deep)


_Loader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_duplicates)


def normalize_text(text: str) -> str:
    """The form a prompt is compared and sent in: Unix newlines, no leading or trailing blank space."""
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def find_file(directory: Path | None = None) -> Path:
    path = (directory or Path.cwd()) / FILENAME
    if not path.is_file():
        raise CliError(f"There is no {FILENAME} in {path.parent}.", "Create one with `verano init`, or pass --file.")
    return path


def load(path: Path) -> Loaded:
    path = path.resolve()
    if not path.is_file():
        raise CliError(f"{path} does not exist.", "Create it with `verano init`.")
    if path.stat().st_size > MAX_YAML_BYTES:
        raise CliError(f"{path.name} is larger than {MAX_YAML_BYTES // 1000} KB; that is not a prompt list.")
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CliError(f"{path.name} is not UTF-8 text.") from exc
    data, root_node = _parse(path, text)
    problems: list[Problem] = []
    try:
        spec = VeranoFile.model_validate(data)
    except ValidationError as error:
        raise SpecError(path, _explain(error, data, root_node)) from None
    root = path.parent
    prompts = _resolve(spec, root, root_node, problems)
    if problems:
        raise SpecError(path, problems)
    return Loaded(path=path, root=root, file=spec, prompts=prompts, warnings=_warnings(prompts))


def _parse(path: Path, text: str) -> tuple[Any, yaml.Node | None]:
    try:
        node = yaml.compose(text, Loader=_Loader)
        data = _Loader(text).get_single_data() if node is not None else None
    except yaml.YAMLError as error:
        mark = getattr(error, "problem_mark", None)
        line = mark.line + 1 if mark else None
        problem = getattr(error, "problem", None) or str(error)
        raise SpecError(path, [Problem(line, "", f"not valid YAML: {problem}")]) from None
    if not isinstance(data, dict):
        raise SpecError(
            path, [Problem(1, "", "the file must start with settings like `version: 1`, not a list or text")]
        )
    return data, node


def _line_of(node: yaml.Node | None, loc: tuple[Any, ...]) -> int | None:
    """The line of the most specific place in the file that `loc` reaches."""
    line = node.start_mark.line + 1 if node is not None else None
    for step in loc:
        if isinstance(node, yaml.MappingNode):
            match = next(((k, v) for k, v in node.value if k.value == step), None)
            if match is None:
                return line
            key_node, node = match
            line = key_node.start_mark.line + 1
        elif isinstance(node, yaml.SequenceNode) and isinstance(step, int) and step < len(node.value):
            node = node.value[step]
            line = node.start_mark.line + 1
        else:
            return line
    return line


KNOWN_KEYS = {
    "version", "project", "keys", "prompts", "name", "source", "file", "line", "system", "system_file", "user",
    "user_file", "params", "task", "data", "models", "judge", "runs", "budget", "type", "goal", "output",
    "allowed_outputs", "output_schema", "constraints", "risks", "golden", "columns", "inputs", "expected_output",
    "rubric", "category", "tags", "input_file", "ignored", "temperature", "top_p", "top_k", "max_tokens", "seed",
    "presence_penalty", "frequency_penalty", "stop", "gate", "min_quality", "min_pass_rate", "max_drop",
}  # fmt: skip


PLAIN = {
    "too_short": "needs at least {min_length} item(s)",
    "string_too_short": "must be at least {min_length} characters",
    "string_too_long": "must be at most {max_length} characters",
    "greater_than_equal": "must be at least {ge}",
    "less_than_equal": "must be at most {le}",
    "greater_than": "must be more than {gt}",
    "less_than": "must be less than {lt}",
    "int_parsing": "must be a whole number",
    "float_parsing": "must be a number",
    "string_type": "must be text",
    "list_type": "must be a list",
    "dict_type": "must be a set of `name: value` lines",
    "int_type": "must be a whole number",
}


def _where(loc: tuple[Any, ...], data: Any) -> str:
    parts: list[str] = []
    cursor: Any = data
    for step in loc:
        if isinstance(step, int):
            item = cursor[step] if isinstance(cursor, list) and step < len(cursor) else None
            name = item.get("name") if isinstance(item, dict) else None
            parts.append(f"[{name if isinstance(name, str) else step}]")
            cursor = item
        else:
            parts.append(f".{step}" if parts else str(step))
            cursor = cursor.get(step) if isinstance(cursor, dict) else None
    return "".join(parts)


def _explain(error: ValidationError, data: Any, node: yaml.Node | None) -> list[Problem]:
    problems = []
    for item in error.errors():
        loc = tuple(item["loc"])
        kind, message = item["type"], item["msg"]
        if kind == "missing":
            message = "is required"
        elif kind == "extra_forbidden":
            guess = difflib.get_close_matches(str(loc[-1]), sorted(KNOWN_KEYS), n=1)
            message = "is not a known setting" + (f". Did you mean '{guess[0]}'?" if guess else "")
        elif kind == "literal_error":
            message = "must be one of: " + str(item.get("ctx", {}).get("expected", "")).replace("'", "")
        elif kind in PLAIN:
            message = PLAIN[kind].format(**item.get("ctx", {}))
        else:
            message = message.removeprefix("Value error, ")
        problems.append(Problem(_line_of(node, loc), _where(loc, data), message))
    return sorted(problems, key=lambda p: (p.line or 0, p.where))


def _inside(root: Path, candidate: Path) -> bool:
    return candidate.resolve().is_relative_to(root.resolve())


def _read_prompt_file(root: Path, name: str, key: str, line: int | None, problems: list[Problem]) -> str | None:
    target = root / name
    where = f"{key}"
    if not _inside(root, target):
        problems.append(Problem(line, where, f"'{name}' is outside this folder; keep prompt files next to verano.yaml"))
    elif not target.is_file():
        problems.append(Problem(line, where, f"'{name}' does not exist"))
    elif target.stat().st_size > MAX_PROMPT_BYTES:
        problems.append(Problem(line, where, f"'{name}' is larger than {MAX_PROMPT_BYTES // 1000} KB"))
    else:
        try:
            text = normalize_text(target.read_text(encoding="utf-8-sig"))
        except UnicodeDecodeError:
            problems.append(Problem(line, where, f"'{name}' is not UTF-8 text"))
            return None
        if text:
            return text
        problems.append(Problem(line, where, f"'{name}' is empty"))
    return None


def _resolve(spec: VeranoFile, root: Path, node: yaml.Node | None, problems: list[Problem]) -> list[ResolvedPrompt]:
    resolved = []
    for index, entry in enumerate(spec.prompts):
        at = ("prompts", index)
        label = f"prompts[{entry.name}]"
        line = _line_of(node, at)

        def where(key: str, *path: str, _at: tuple[Any, ...] = at) -> int | None:
            return _line_of(node, (*_at, *(path or (key,))))

        texts: dict[str, str | None] = {}
        for part in ("system", "user"):
            inline, file = getattr(entry, part), getattr(entry, f"{part}_file")
            if inline is not None:
                texts[part] = normalize_text(inline) or None
                if texts[part] is None:
                    problems.append(Problem(where(part), f"{label}.{part}", "the prompt is empty"))
            elif file is not None:
                texts[part] = _read_prompt_file(root, file, f"{label}.{part}_file", where(f"{part}_file"), problems)
            else:
                texts[part] = None
        golden = _resolve_golden(entry, root, label, where, problems)
        inputs = _resolve_inputs(entry, root, label, where, problems)
        built = _resolve_cases(entry, root, label, where, problems)
        resolved.append(
            ResolvedPrompt(
                entry=entry,
                project_name=f"{spec.project}{SEPARATOR}{entry.name}",
                system=texts["system"],
                user=texts["user"],
                golden=golden,
                inputs=inputs,
                line=line,
                cases=built,
            )
        )
    return resolved


def _resolve_cases(
    entry: PromptEntry, root: Path, label: str, where: Any, problems: list[Problem]
) -> case_tables.Built | None:
    spec = entry.data.cases
    if spec is None:
        return None
    line, key = where("data", "data", "cases", "file"), f"{label}.data.cases.file"
    path = root / spec.file
    if not _inside(root, path):
        problems.append(Problem(line, key, f"'{spec.file}' is outside this folder"))
    elif not path.is_file():
        problems.append(Problem(line, key, f"'{spec.file}' does not exist"))
    elif path.suffix.lower() not in case_tables.SUFFIXES:
        hint = " Save it as CSV first." if path.suffix.lower() == ".xlsx" else ""
        problems.append(Problem(line, key, f"'{path.name}' can't be read as rows (use csv, tsv, json or jsonl).{hint}"))
    else:
        try:
            built = case_tables.build(case_tables.read_rows(path), spec)
        except (ValueError, UnicodeDecodeError) as exc:
            problems.append(Problem(line, key, f"'{path.name}': {exc}"))
            return None
        for message in built.problems:
            problems.append(Problem(line, key, f"'{path.name}': {message}"))
        return built
    return None


def _resolve_golden(entry: PromptEntry, root: Path, label: str, where: Any, problems: list[Problem]) -> Path | None:
    if entry.data.golden is None:
        return None
    path = root / entry.data.golden
    line = where("data", "data", "golden")
    key = f"{label}.data.golden"
    if not _inside(root, path):
        problems.append(Problem(line, key, f"'{entry.data.golden}' is outside this folder"))
    elif not path.is_file():
        problems.append(Problem(line, key, f"'{entry.data.golden}' does not exist"))
    elif path.suffix.lower() not in GOLDEN_SUFFIXES:
        allowed = ", ".join(sorted(GOLDEN_SUFFIXES))
        problems.append(Problem(line, key, f"'{path.name}' is not a table file (use {allowed})"))
    else:
        return path.resolve()
    return None


def _resolve_inputs(entry: PromptEntry, root: Path, label: str, where: Any, problems: list[Problem]) -> list[Path]:
    found: list[Path] = []
    line = where("data", "data", "inputs")
    for pattern in entry.data.inputs:
        matches = sorted(Path(m) for m in glob.glob(str(root / pattern), recursive=True))
        files = [m for m in matches if m.is_file()]
        outside = [m for m in files if not _inside(root, m)]
        if outside:
            problems.append(Problem(line, f"{label}.data.inputs", f"'{pattern}' reaches outside this folder"))
        elif not files:
            problems.append(Problem(line, f"{label}.data.inputs", f"'{pattern}' matches no files"))
        found += [f.resolve() for f in files if f.resolve() not in found]
    if len(found) > MAX_INPUT_FILES:
        problems.append(
            Problem(line, f"{label}.data.inputs", f"{len(found)} files; at most {MAX_INPUT_FILES} per prompt")
        )
    return found


def _warnings(prompts: list[ResolvedPrompt]) -> list[str]:
    notes = []
    for p in prompts:
        if p.cases is not None and p.cases.skipped:
            shown = "; ".join(p.cases.skipped[:3]) + ("; …" if len(p.cases.skipped) > 3 else "")
            notes.append(f"{p.entry.name}: {len(p.cases.skipped)} rows skipped ({shown}).")
        if "TODO" in p.entry.task.goal.upper() or any("TODO" in m.upper() for m in p.entry.models):
            notes.append(f"{p.entry.name}: still has TODO values to fill in (task goal or model).")
        if p.golden is None and not p.inputs and p.cases is None:
            notes.append(
                f"{p.entry.name}: no data. `verano push` sets the project up, but there is nothing to run yet."
            )
        if p.golden is None and p.inputs:
            notes.append(f"{p.entry.name}: input files without a golden file have no correct answers to score against.")
        if p.entry.judge is None and p.entry.task.type in {"summarization", "generation", "conversation"}:
            notes.append(f"{p.entry.name}: this kind of task is usually scored by a judge model; add `judge:`.")
    return notes
