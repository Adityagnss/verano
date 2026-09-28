"""
Evaluator-set use cases: create a version from chosen evaluators, read one, and edit one.

A project keeps one evaluator set; every change (including the first, automatic selection
from the Task Spec) is a new immutable version, so an evaluation run always names the
exact rubrics and thresholds it scored with. Editing a version never changes it; it saves
the edited evaluators as the next version.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFound
from app.core.ids import uuid7
from app.core.security import Principal
from app.modules.evaluation.models import EvaluatorSet, EvaluatorSetVersion
from app.modules.evaluation.repository import EvaluatorRepository
from app.modules.evaluation.schemas import (
    EvaluatorConfigIn,
    EvaluatorConfigOut,
    EvaluatorSetUpdate,
    EvaluatorSetVersionOut,
)

SET_NAME = "Evaluators"
VERSION_NOT_FOUND = "This evaluator set version doesn't exist in this project."


class EvaluatorSetService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = EvaluatorRepository(session)

    async def create_version(
        self,
        project_id: uuid.UUID,
        evaluators: list[EvaluatorConfigIn],
        change_reason: str | None,
        principal: Principal | None = None,
    ) -> EvaluatorSetVersionOut:
        evaluator_set = await self._repo.project_set(project_id)
        if evaluator_set is None:
            evaluator_set = EvaluatorSet(project_id=project_id, name=SET_NAME)
            await self._repo.add(evaluator_set)
        version = EvaluatorSetVersion(
            evaluator_set_id=evaluator_set.id,
            version=await self._repo.next_version_number(evaluator_set.id),
            change_reason=change_reason,
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
        await self._version(project_id, version_id)
        return await self.create_version(project_id, body.evaluators, body.change_reason, principal)

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
            evaluators=[EvaluatorConfigOut.model_validate(config) for config in configs],
            created_at=version.created_at,
        )
