"""
"Update checks to the current default set" use cases (ADR 0039): preview what the update would add, change and remove
for a project's evaluator-set version, then apply it on confirmation as a new version with a note.

Nothing is applied by the preview. Applying never removes a check that is not named, never touches a check the
defaults do not know (the user's own), and when nothing would change it creates no new version. Older versions and the
runs scored with them stay as they were, so old and new runs are never mixed up (the compare rule keeps them apart).
"""

import uuid
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.datafiles import load_yaml
from app.core.errors import ValidationFailed
from app.core.security import Principal
from app.modules.datasets.service import DatasetService
from app.modules.evaluation.schemas import EvaluatorConfigIn
from app.modules.evaluation.service import EvaluatorSetService
from app.modules.generator.defaults_schemas import (
    CheckLineOut,
    DefaultsApplied,
    DefaultsApply,
    DefaultsPreviewOut,
    DifferenceOut,
)
from app.modules.generator.defaults_update import (
    Action,
    CheckLine,
    apply_update,
    plan_update,
    version_note,
)
from app.modules.generator.domain import RULES_JUDGE, EvaluatorCatalog, EvaluatorChoice, select_evaluators
from app.modules.generator.repository import TaskSpecRepository
from app.modules.generator.schemas import TaskSpec
from app.modules.projects.schemas import ProjectOut

EVALUATOR_CATALOG = Path(__file__).parents[1] / "evaluation" / "config" / "catalog.yaml"
NO_SPEC = "This project has no Task Spec yet, so there are no default checks to compare with. Set up the task first."
NOTES = {
    Action.ADD: "New in the current defaults.",
    Action.CHANGE: "Differs from the current default; the update would replace it with the default.",
    Action.SAME: "Already matches the current default.",
    Action.KEEP: "A check you added. It stays exactly as it is.",
    Action.REMOVE: "The current defaults would not choose this check for this task. It stays unless you remove it.",
}
EDITED_NOTE = " You changed it, so look before removing it."


def family_of(catalog: EvaluatorCatalog) -> dict[str, EvaluatorChoice]:
    """One template per check name the defaults can ever choose (for any task type)."""
    defaults = catalog.defaults
    templates = [catalog.constraints, *(t for group in catalog.task_types.values() for t in group)]
    found: dict[str, EvaluatorChoice] = {}
    for template in templates:
        found.setdefault(
            template.name,
            EvaluatorChoice(
                name=template.name,
                version=template.version,
                config={"kind": template.kind, **template.config},
                threshold=template.threshold if template.threshold is not None else defaults["threshold"],
                weight=template.weight if template.weight is not None else defaults["weight"],
                required=template.required if template.required is not None else defaults["required"],
            ),
        )
    found[RULES_JUDGE] = EvaluatorChoice(
        name=RULES_JUDGE,
        version="1",
        config={"kind": "deepeval", "metric": "g_eval"},
        threshold=defaults["threshold"],
        weight=defaults["weight"],
        required=defaults["required"],
    )
    return found


def summary_of(lines: list[CheckLine]) -> str:
    counts = {action: sum(1 for line in lines if line.action is action) for action in Action}
    if not (counts[Action.ADD] or counts[Action.CHANGE] or counts[Action.REMOVE]):
        return "Your checks already match the current defaults."
    parts = [
        f"{counts[action]} {label}"
        for action, label in (
            (Action.ADD, "to add"),
            (Action.CHANGE, "to change"),
            (Action.REMOVE, "that the defaults would not choose (kept unless you remove them)"),
        )
        if counts[action]
    ]
    return ", ".join(parts).capitalize() + "."


class EvaluatorDefaultsService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._datasets = DatasetService(session, settings)
        self._evaluators = EvaluatorSetService(session)
        self._specs = TaskSpecRepository(session)
        self._catalog = load_yaml(EVALUATOR_CATALOG, EvaluatorCatalog)

    async def preview(self, project: ProjectOut, version_id: uuid.UUID) -> DefaultsPreviewOut:
        spec, _, _, lines = await self._plan(project, version_id)
        return DefaultsPreviewOut(
            evaluator_set_version_id=version_id,
            task_type=spec.task_type.value,
            up_to_date=all(line.action in (Action.SAME, Action.KEEP) for line in lines),
            summary=summary_of(lines),
            lines=[
                CheckLineOut(
                    name=line.name,
                    action=line.action,
                    edited=line.edited,
                    differences=[
                        DifferenceOut(field=d.field, before=d.before, after=d.after) for d in line.differences
                    ],
                    note=NOTES[line.action] + (EDITED_NOTE if line.edited else ""),
                )
                for line in lines
            ],
        )

    async def apply(
        self, project: ProjectOut, principal: Principal, version_id: uuid.UUID, body: DefaultsApply
    ) -> DefaultsApplied:
        _, current, defaults, lines = await self._plan(project, version_id)
        skip, remove = set(body.skip), set(body.remove)
        evaluators = apply_update(current, defaults, lines, skip, remove)
        note = version_note(lines, skip, remove)
        created = await self._evaluators.with_changes(
            project.id, version_id, principal, evaluators=evaluators, change_reason=note[:2000]
        )
        if created.id != version_id:
            draft = await self._datasets.find_draft(project.id)
            if draft is not None and draft.evaluator_set_version_id == version_id:
                await self._datasets.update_version(draft.id, {"evaluator_set_version_id": created.id})
        return DefaultsApplied(version=created, note=note, created=created.id != version_id)

    async def _plan(
        self, project: ProjectOut, version_id: uuid.UUID
    ) -> tuple[TaskSpec, list[EvaluatorConfigIn], list[EvaluatorChoice], list[CheckLine]]:
        version = await self._evaluators.get_version(project.id, version_id)
        dataset = await self._datasets.current(project.id)
        record = await self._specs.get(project.id, dataset.task_spec_id) if dataset.task_spec_id else None
        if record is None:
            raise ValidationFailed(NO_SPEC)
        spec = TaskSpec.model_validate(record.spec)
        current = [
            EvaluatorConfigIn.model_validate(e.model_dump(exclude={"id", "position"})) for e in version.evaluators
        ]
        defaults = select_evaluators(spec, self._catalog)
        return spec, current, defaults, plan_update(current, defaults, family_of(self._catalog))
