"""
Evaluator-set use cases: create a version from chosen evaluators, read one, and edit one.

A project keeps one evaluator set; every change (including the first, automatic selection
from the Task Spec) is a new immutable version, so an evaluation run always names the
exact rubrics and thresholds it scored with. Editing a version never changes it; it saves
the edited evaluators as the next version.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFound, ValidationFailed
from app.core.ids import uuid7
from app.core.security import Principal
from app.modules.evaluation.models import EvaluatorSet, EvaluatorSetVersion
from app.modules.evaluation.plugins.rules import RULES
from app.modules.evaluation.repository import EvaluatorRepository
from app.modules.evaluation.schemas import (
    EvaluatorConfigIn,
    EvaluatorConfigOut,
    EvaluatorSetUpdate,
    EvaluatorSetVersionOut,
    JudgeCallOut,
    JudgeChoice,
)
from app.modules.gateway.models import LLMCall

SET_NAME = "Evaluators"
VERSION_NOT_FOUND = "This evaluator set version doesn't exist in this project."
UNKNOWN_CHECK = "There is no check called {name}."


def _checks(version: EvaluatorSetVersionOut) -> list[dict[str, object]]:
    """What a version checks, without its identity: two versions with equal checks score alike."""
    return [e.model_dump(exclude={"id", "position"}) for e in version.evaluators]


def judge_call_out(call: LLMCall) -> JudgeCallOut:
    labels = call.labels or {}
    run = labels.get("evaluation_run_id")
    return JudgeCallOut(
        id=call.id,
        evaluator=labels.get("evaluator"),
        evaluation_run_id=uuid.UUID(run) if run else None,
        preview=labels.get("preview") == "true",
        model=call.model,
        status=call.status.value,
        request_messages=call.request_messages,
        output_text=call.output_text,
        error_message=call.error_message,
        cost=call.cost,
        created_at=call.created_at,
    )


class EvaluatorSetService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = EvaluatorRepository(session)

    async def create_version(
        self,
        project_id: uuid.UUID,
        evaluators: list[EvaluatorConfigIn],
        change_reason: str | None,
        principal: Principal | None = None,
        judge: JudgeChoice | None = None,
    ) -> EvaluatorSetVersionOut:
        evaluator_set = await self._repo.project_set(project_id)
        if evaluator_set is None:
            evaluator_set = EvaluatorSet(project_id=project_id, name=SET_NAME)
            await self._repo.add(evaluator_set)
        version = EvaluatorSetVersion(
            evaluator_set_id=evaluator_set.id,
            version=await self._repo.next_version_number(evaluator_set.id),
            change_reason=change_reason,
            judge=judge.model_dump(mode="json") if judge else None,
            created_by=principal.user_id if principal else None,
        )
        await self._repo.add(version)
        await self._repo.insert_configs(
            [
                {"id": uuid7(), "evaluator_set_version_id": version.id, "position": position, **item.model_dump()}
                for position, item in enumerate(evaluators)
            ]
        )
        return await self._out(version)

    async def get_version(self, project_id: uuid.UUID, version_id: uuid.UUID) -> EvaluatorSetVersionOut:
        return await self._out(await self._version(project_id, version_id))

    async def edit(
        self, project_id: uuid.UUID, version_id: uuid.UUID, body: EvaluatorSetUpdate, principal: Principal
    ) -> EvaluatorSetVersionOut:
        previous = await self._version(project_id, version_id)
        kept = JudgeChoice.model_validate(previous.judge) if previous.judge else None
        return await self.create_version(project_id, body.evaluators, body.change_reason, principal, body.judge or kept)

    async def with_changes(
        self,
        project_id: uuid.UUID,
        base_id: uuid.UUID,
        principal: Principal | None,
        *,
        evaluators: list[EvaluatorConfigIn] | None = None,
        judge: JudgeChoice | None = None,
        change_reason: str | None = None,
    ) -> EvaluatorSetVersionOut:
        """The base version with other checks and/or another judge: the base itself when nothing changes, an
        existing version that already matches, or a new one. The frozen dataset is never touched, and asking
        for the same thing twice does not pile up versions."""
        base = await self._out(await self._version(project_id, base_id))
        if evaluators is not None:
            for item in evaluators:
                if item.config.get("kind") not in ("deepeval", "code") and item.evaluator_name not in RULES:
                    raise ValidationFailed(UNKNOWN_CHECK.format(name=item.evaluator_name))
        wanted = [e.model_dump() for e in evaluators] if evaluators is not None else _checks(base)
        wanted_judge = judge or base.judge
        if wanted == _checks(base) and wanted_judge == base.judge:
            return base
        for existing in await self._repo.versions(base.evaluator_set_id):
            candidate = await self._out(existing)
            if candidate.judge == wanted_judge and _checks(candidate) == wanted:
                return candidate
        edits = evaluators or [
            EvaluatorConfigIn.model_validate(e.model_dump(exclude={"id", "position"})) for e in base.evaluators
        ]
        edited_checks = wanted != _checks(base)
        judge_name = wanted_judge.model if wanted_judge else "none"
        if change_reason:
            reason = change_reason
        elif edited_checks and wanted_judge != base.judge:
            reason = f"Checks edited and judge changed to {judge_name}."
        elif edited_checks:
            reason = "Checks edited."
        else:
            reason = f"Judge changed to {judge_name}."
        return await self.create_version(project_id, edits, reason, principal, wanted_judge)

    async def with_judge(
        self, project_id: uuid.UUID, base_id: uuid.UUID, judge: JudgeChoice, principal: Principal | None
    ) -> EvaluatorSetVersionOut:
        return await self.with_changes(project_id, base_id, principal, judge=judge)

    async def judge_of(self, version_id: uuid.UUID) -> JudgeChoice | None:
        stored = await self._repo.judge_of(version_id)
        return JudgeChoice.model_validate(stored) if stored else None

    async def _version(self, project_id: uuid.UUID, version_id: uuid.UUID) -> EvaluatorSetVersion:
        version = await self._repo.version(project_id, version_id)
        if version is None:
            raise NotFound(VERSION_NOT_FOUND)
        return version

    async def _out(self, version: EvaluatorSetVersion) -> EvaluatorSetVersionOut:
        configs = await self._repo.configs(version.id)
        return EvaluatorSetVersionOut(
            id=version.id,
            evaluator_set_id=version.evaluator_set_id,
            version=version.version,
            change_reason=version.change_reason,
            judge=JudgeChoice.model_validate(version.judge) if version.judge else None,
            evaluators=[EvaluatorConfigOut.model_validate(config) for config in configs],
            created_at=version.created_at,
        )
