"""
Updating a project's checks to the current default set (ADR 0039). Pure: no I/O.

Checks made under older defaults keep their old text and settings until the user asks for the update. The plan lines
up the checks the project has with the checks the current defaults would choose for its Task Spec:

- *add*: a default the project does not have;
- *change*: the project has it, but its text or settings differ from the current default (every difference is shown);
- *same*: nothing to do;
- *keep*: a check the defaults do not know (one the user added: a gallery judge, a code check, a rule): never touched;
- *remove*: a check from the default family that the current defaults would not choose for this task. It is only
  removed when the user names it, and a check whose text or settings the user changed (`edited`) is flagged.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.core.errors import ValidationFailed
from app.core.text import bound
from app.modules.evaluation.schemas import EvaluatorConfigIn
from app.modules.generator.domain import EvaluatorChoice

TOLERANCE = 1e-9
SHOWN_CHARS = 400
UNKNOWN_NAME = "There is no check called '{name}' in this update."
NOT_REMOVABLE = "'{name}' is not a check the update would remove."
NOT_CHANGEABLE = "'{name}' has no change to leave out."


class Action(StrEnum):
    ADD = "add"
    CHANGE = "change"
    SAME = "same"
    KEEP = "keep"
    REMOVE = "remove"


@dataclass(frozen=True)
class Difference:
    field: str
    before: str | None
    after: str | None


@dataclass(frozen=True)
class CheckLine:
    name: str
    action: Action
    edited: bool = False
    differences: list[Difference] = field(default_factory=list)


def _show(value: Any) -> str | None:
    if value is None:
        return None
    return bound(value if isinstance(value, str) else str(value), SHOWN_CHARS)[0]


def _differs(before: Any, after: Any) -> bool:
    if isinstance(before, int | float) and isinstance(after, int | float) and not isinstance(before, bool):
        return abs(float(before) - float(after)) > TOLERANCE
    return bool(before != after)


def differences(current: EvaluatorConfigIn, default: EvaluatorChoice) -> list[Difference]:
    found: list[Difference] = []
    if current.evaluator_version != default.version:
        found.append(Difference("version", current.evaluator_version, default.version))
    for name in sorted(set(current.config) | set(default.config)):
        if _differs(current.config.get(name), default.config.get(name)):
            found.append(Difference(name, _show(current.config.get(name)), _show(default.config.get(name))))
    for name in ("threshold", "weight", "required"):
        if _differs(getattr(current, name), getattr(default, name)):
            found.append(Difference(name, _show(getattr(current, name)), _show(getattr(default, name))))
    return found


def plan_update(
    current: Sequence[EvaluatorConfigIn], defaults: Sequence[EvaluatorChoice], family: dict[str, EvaluatorChoice]
) -> list[CheckLine]:
    """What the update would do, one line per check. `family` has one template per check name the defaults ever
    choose, to tell a user's edit of a default check (its text, threshold or required flag; weights follow the Task
    Spec and are not counted) from a check of their own."""
    have = {check.evaluator_name: check for check in current}
    wanted = {default.name for default in defaults}
    lines: list[CheckLine] = []
    for default in defaults:
        check = have.get(default.name)
        if check is None:
            lines.append(CheckLine(default.name, Action.ADD))
            continue
        found = differences(check, default)
        lines.append(CheckLine(default.name, Action.CHANGE if found else Action.SAME, differences=found))
    for check in current:
        if check.evaluator_name in wanted:
            continue
        template = family.get(check.evaluator_name)
        if template is None:
            lines.append(CheckLine(check.evaluator_name, Action.KEEP))
        else:
            own = {*template.config, "threshold", "required"}
            edited = any(d.field in own for d in differences(check, template))
            lines.append(CheckLine(check.evaluator_name, Action.REMOVE, edited=edited))
    return lines


def apply_update(
    current: Sequence[EvaluatorConfigIn],
    defaults: Sequence[EvaluatorChoice],
    lines: Sequence[CheckLine],
    skip: set[str],
    remove: set[str],
) -> list[EvaluatorConfigIn]:
    """The checks after the update: the defaults (the project's own version of a changed check when it is in `skip`),
    then the project's other checks, minus those named in `remove`. Nothing is removed unless it is named."""
    by_name = {line.name: line for line in lines}
    for name in skip:
        if name not in by_name:
            raise ValidationFailed(UNKNOWN_NAME.format(name=name))
        if by_name[name].action not in (Action.CHANGE, Action.ADD):
            raise ValidationFailed(NOT_CHANGEABLE.format(name=name))
    for name in remove:
        if name not in by_name:
            raise ValidationFailed(UNKNOWN_NAME.format(name=name))
        if by_name[name].action is not Action.REMOVE:
            raise ValidationFailed(NOT_REMOVABLE.format(name=name))
    have = {check.evaluator_name: check for check in current}
    result: list[EvaluatorConfigIn] = []
    for default in defaults:
        if default.name in skip:
            if default.name in have:
                result.append(have[default.name])
            continue
        result.append(
            EvaluatorConfigIn(
                evaluator_name=default.name,
                evaluator_version=default.version,
                config=default.config,
                threshold=default.threshold,
                weight=default.weight,
                required=default.required,
            )
        )
    wanted = {default.name for default in defaults}
    result.extend(check for check in current if check.evaluator_name not in wanted | remove)
    return result


def version_note(lines: Sequence[CheckLine], skip: set[str], remove: set[str]) -> str:
    """The note kept with the new evaluator-set version: what the update did, in one sentence."""
    added = [line.name for line in lines if line.action is Action.ADD and line.name not in skip]
    changed = [line.name for line in lines if line.action is Action.CHANGE and line.name not in skip]
    left = [
        line.name for line in lines if line.name in skip or (line.action is Action.REMOVE and line.name not in remove)
    ]
    groups = (("added", added), ("changed", changed), ("removed", sorted(remove)), ("left as before", left))
    parts = [f"{label}: {', '.join(names)}" for label, names in groups if names]
    return "Updated to the current default checks. " + "; ".join(parts) + "." if parts else "Already up to date."
