"""Improvement data access: sessions, their candidates, and failure clusters per evaluation run."""

import uuid
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.analysis.models import FailureCluster
from app.modules.assistant.models import OptimizationSession, PromptCandidate


class AssistantRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, row: OptimizationSession | PromptCandidate | FailureCluster) -> None:
        self._session.add(row)
        await self._session.flush()

    async def session(self, session_id: uuid.UUID, project_id: uuid.UUID | None = None) -> OptimizationSession | None:
        query = select(OptimizationSession).where(OptimizationSession.id == session_id)
        if project_id is not None:
            query = query.where(OptimizationSession.project_id == project_id)
        return await self._session.scalar(query.execution_options(populate_existing=True))

    async def latest_for(self, project_id: uuid.UUID, experiment_id: uuid.UUID) -> OptimizationSession | None:
        query = (
            select(OptimizationSession)
            .where(
                OptimizationSession.project_id == project_id,
                OptimizationSession.baseline_experiment_id == experiment_id,
            )
            .order_by(OptimizationSession.id.desc())
            .limit(1)
        )
        return await self._session.scalar(query)

    async def update_session(self, session_id: uuid.UUID, values: dict[str, Any], stage_was: str | None = None) -> bool:
        query = update(OptimizationSession).where(OptimizationSession.id == session_id)
        if stage_was is not None:
            query = query.where(OptimizationSession.stage == stage_was)
        result = await self._session.execute(query.values(**values))
        return bool(getattr(result, "rowcount", 0))

    async def sessions(self, project_id: uuid.UUID, limit: int) -> list[OptimizationSession]:
        query = (
            select(OptimizationSession)
            .where(OptimizationSession.project_id == project_id)
            .order_by(OptimizationSession.id.desc())
            .limit(limit)
        )
        return list((await self._session.scalars(query)).all())

    async def candidates(self, session_id: uuid.UUID) -> list[PromptCandidate]:
        query = select(PromptCandidate).where(PromptCandidate.session_id == session_id).order_by(PromptCandidate.id)
        return list((await self._session.scalars(query.execution_options(populate_existing=True))).all())

    async def candidate_for_experiment(self, experiment_id: uuid.UUID) -> PromptCandidate | None:
        query = select(PromptCandidate).where(
            (PromptCandidate.optimize_experiment_id == experiment_id)
            | (PromptCandidate.holdout_experiment_id == experiment_id)
            | (PromptCandidate.quick_experiment_id == experiment_id)
        )
        return await self._session.scalar(query)

    async def update_candidate(self, candidate_id: uuid.UUID, values: dict[str, Any]) -> None:
        await self._session.execute(update(PromptCandidate).where(PromptCandidate.id == candidate_id).values(**values))

    async def replace_clusters(self, evaluation_run_id: uuid.UUID) -> None:
        await self._session.execute(delete(FailureCluster).where(FailureCluster.evaluation_run_id == evaluation_run_id))

    async def clusters(self, evaluation_run_id: uuid.UUID) -> list[FailureCluster]:
        query = select(FailureCluster).where(FailureCluster.evaluation_run_id == evaluation_run_id)
        return list((await self._session.scalars(query.order_by(FailureCluster.size.desc()))).all())
