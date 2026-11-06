"""
Evaluation data access: evaluator sets, their immutable versions and each version's
evaluators; evaluation runs (one per scoring pass) and their scores.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.evaluation.models import (
    EvaluationRun,
    EvaluatorConfig,
    EvaluatorSet,
    EvaluatorSetVersion,
    HumanLabel,
    JudgeCacheEntry,
    Score,
)
from app.modules.evaluation.schemas import EvaluationRunStatus, EvaluationTrigger
from app.modules.gateway.models import LLMCall
from app.modules.gateway.schemas import CallPurpose


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

    async def versions(self, set_id: uuid.UUID) -> list[EvaluatorSetVersion]:
        query = (
            select(EvaluatorSetVersion)
            .where(EvaluatorSetVersion.evaluator_set_id == set_id)
            .order_by(EvaluatorSetVersion.version.desc())
        )
        return list((await self._session.scalars(query)).all())

    async def judge_of(self, version_id: uuid.UUID) -> dict[str, Any] | None:
        judge: dict[str, Any] | None = await self._session.scalar(
            select(EvaluatorSetVersion.judge).where(EvaluatorSetVersion.id == version_id)
        )
        return judge

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

    async def claim_run(self, run_id: uuid.UUID, lease_until: datetime | None = None) -> EvaluationRun | None:
        """Moves a pending pass to running; None when it was already claimed (a redelivered job)."""
        query = (
            update(EvaluationRun)
            .where(EvaluationRun.id == run_id, EvaluationRun.status == EvaluationRunStatus.PENDING)
            .values(status=EvaluationRunStatus.RUNNING, lease_expires_at=lease_until)
            .returning(EvaluationRun)
        )
        return await self._session.scalar(query)

    async def finish_run(self, run_id: uuid.UUID, status: EvaluationRunStatus, completed_at: datetime) -> None:
        await self._session.execute(
            update(EvaluationRun)
            .where(EvaluationRun.id == run_id)
            .values(status=status, completed_at=completed_at, lease_expires_at=None)
        )

    async def answers_scored(self, experiment_id: uuid.UUID) -> int:
        """How many answers the scoring pass that is running now has finished (their scores are saved as they go)."""
        running = (
            select(EvaluationRun.id)
            .where(EvaluationRun.experiment_id == experiment_id, EvaluationRun.status == EvaluationRunStatus.RUNNING)
            .scalar_subquery()
        )
        count = await self._session.scalar(
            select(func.count(func.distinct(Score.test_case_run_id))).where(Score.evaluation_run_id == running)
        )
        return int(count or 0)

    async def insert_scores(self, rows: list[dict[str, Any]]) -> None:
        for start in range(0, len(rows), 1000):
            await self._session.execute(insert(Score), rows[start : start + 1000])

    async def scores(self, experiment_id: uuid.UUID, run_id: uuid.UUID) -> list[Score]:
        query = select(Score).where(Score.experiment_id == experiment_id, Score.evaluation_run_id == run_id)
        return list((await self._session.scalars(query)).all())

    async def judge_calls(self, experiment_id: uuid.UUID, test_case_run_id: uuid.UUID) -> list[LLMCall]:
        query = (
            select(LLMCall)
            .where(
                LLMCall.experiment_id == experiment_id,
                LLMCall.test_case_run_id == test_case_run_id,
                LLMCall.purpose == CallPurpose.JUDGE,
            )
            .order_by(LLMCall.started_at, LLMCall.id)
        )
        return list((await self._session.scalars(query)).all())

    async def extend_run_lease(self, run_id: uuid.UUID, until: datetime) -> None:
        await self._session.execute(
            update(EvaluationRun)
            .where(EvaluationRun.id == run_id, EvaluationRun.status == EvaluationRunStatus.RUNNING)
            .values(lease_expires_at=until)
        )

    async def scored_call_ids(self, run_id: uuid.UUID) -> set[uuid.UUID]:
        """Answers this pass has already scored, so a pass handed to another worker skips them."""
        rows = await self._session.execute(
            select(func.distinct(Score.test_case_run_id)).where(Score.evaluation_run_id == run_id)
        )
        return {row[0] for row in rows.all()}

    async def release_expired_runs(self, now: datetime) -> list[tuple[uuid.UUID, uuid.UUID, str]]:
        """Passes whose worker stopped renewing the claim go back to pending: (run id, experiment id, trigger)."""
        result = await self._session.execute(
            update(EvaluationRun)
            .where(
                EvaluationRun.status == EvaluationRunStatus.RUNNING,
                EvaluationRun.lease_expires_at.is_not(None),
                EvaluationRun.lease_expires_at <= now,
            )
            .values(status=EvaluationRunStatus.PENDING, lease_expires_at=None)
            .returning(EvaluationRun.id, EvaluationRun.experiment_id, EvaluationRun.trigger)
        )
        return [(row[0], row[1], EvaluationTrigger(row[2]).value) for row in result.all()]


class LabelRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def set(
        self, experiment_id: uuid.UUID, test_case_run_id: uuid.UUID, user_id: uuid.UUID, verdict: str, note: str | None
    ) -> HumanLabel:
        """One label per person per answer: a second label from the same person replaces their first."""
        statement = (
            pg_insert(HumanLabel)
            .values(
                experiment_id=experiment_id,
                test_case_run_id=test_case_run_id,
                user_id=user_id,
                verdict=verdict,
                note=note,
            )
            .on_conflict_do_update(
                index_elements=["experiment_id", "test_case_run_id", "user_id"],
                set_={"verdict": verdict, "note": note, "updated_at": func.now()},
            )
            .returning(HumanLabel.id)
        )
        label_id = await self._session.scalar(statement)
        row = await self._session.scalar(
            select(HumanLabel).where(HumanLabel.id == label_id).execution_options(populate_existing=True)
        )
        assert row is not None
        return row

    async def remove(self, experiment_id: uuid.UUID, test_case_run_id: uuid.UUID, user_id: uuid.UUID) -> None:
        await self._session.execute(
            delete(HumanLabel).where(
                HumanLabel.experiment_id == experiment_id,
                HumanLabel.test_case_run_id == test_case_run_id,
                HumanLabel.user_id == user_id,
            )
        )

    async def for_experiment(self, experiment_id: uuid.UUID) -> list[HumanLabel]:
        query = select(HumanLabel).where(HumanLabel.experiment_id == experiment_id).order_by(HumanLabel.created_at)
        return list((await self._session.scalars(query.execution_options(populate_existing=True))).all())


class JudgeCacheRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, key: str) -> JudgeCacheEntry | None:
        return await self._session.scalar(select(JudgeCacheEntry).where(JudgeCacheEntry.key == key))

    async def put(self, key: str, evaluator_name: str, value: float, passed: bool, reason: str) -> None:
        """Stores a judge's result; the same content judged twice at once keeps the first."""
        await self._session.execute(
            pg_insert(JudgeCacheEntry)
            .values(key=key, evaluator_name=evaluator_name, value=value, passed=passed, reason=reason)
            .on_conflict_do_nothing(index_elements=["key"])
        )

    async def count_hit(self, key: str) -> None:
        await self._session.execute(
            update(JudgeCacheEntry).where(JudgeCacheEntry.key == key).values(hits=JudgeCacheEntry.hits + 1)
        )
