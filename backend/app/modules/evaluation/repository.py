"""
Evaluation data access: evaluator sets, their immutable versions and each version's
evaluators; evaluation runs (one per scoring pass) and their scores.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.evaluation.models import EvaluationRun, EvaluatorConfig, EvaluatorSet, EvaluatorSetVersion, Score
from app.modules.evaluation.schemas import EvaluationRunStatus


class EvaluatorRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, row: EvaluatorSet | EvaluatorSetVersion) -> None:
        self._session.add(row)
        await self._session.flush()

    async def project_set(self, project_id: uuid.UUID) -> EvaluatorSet | None:
        query = select(EvaluatorSet).where(EvaluatorSet.project_id == project_id).order_by(EvaluatorSet.id).limit(1)
        return await self._session.scalar(query)

    async def version(self, project_id: uuid.UUID, version_id: uuid.UUID) -> EvaluatorSetVersion | None:
        query = (
            select(EvaluatorSetVersion)
            .join(EvaluatorSet, EvaluatorSet.id == EvaluatorSetVersion.evaluator_set_id)
            .where(EvaluatorSetVersion.id == version_id, EvaluatorSet.project_id == project_id)
        )
        return await self._session.scalar(query)

    async def next_version_number(self, set_id: uuid.UUID) -> int:
        current = await self._session.scalar(
            select(func.max(EvaluatorSetVersion.version)).where(EvaluatorSetVersion.evaluator_set_id == set_id)
        )
        return int(current or 0) + 1

    async def insert_configs(self, rows: list[dict[str, Any]]) -> None:
        await self._session.execute(insert(EvaluatorConfig), rows)

    async def configs(self, version_id: uuid.UUID) -> list[EvaluatorConfig]:
        query = (
            select(EvaluatorConfig)
            .where(EvaluatorConfig.evaluator_set_version_id == version_id)
            .order_by(EvaluatorConfig.position)
        )
        return list((await self._session.scalars(query)).all())


class ScoreRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_run(self, row: EvaluationRun) -> None:
        self._session.add(row)
        await self._session.flush()

    async def runs(self, experiment_id: uuid.UUID) -> list[EvaluationRun]:
        query = select(EvaluationRun).where(EvaluationRun.experiment_id == experiment_id)
        return list((await self._session.scalars(query.order_by(EvaluationRun.id.desc()))).all())

    async def finish_run(self, run_id: uuid.UUID, status: EvaluationRunStatus, completed_at: datetime) -> None:
        await self._session.execute(
            update(EvaluationRun).where(EvaluationRun.id == run_id).values(status=status, completed_at=completed_at)
        )

    async def insert_scores(self, rows: list[dict[str, Any]]) -> None:
        for start in range(0, len(rows), 1000):
            await self._session.execute(insert(Score), rows[start : start + 1000])

    async def scores(self, experiment_id: uuid.UUID, run_id: uuid.UUID) -> list[Score]:
        query = select(Score).where(Score.experiment_id == experiment_id, Score.evaluation_run_id == run_id)
        return list((await self._session.scalars(query)).all())
