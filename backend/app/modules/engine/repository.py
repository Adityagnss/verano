"""
Engine data access: experiments, their status events, and test-case runs.

Status changes are compare-and-set (`UPDATE ... WHERE status = current`), so two workers
can never both move an experiment out of the same state. Test-case runs are inserted with
ON CONFLICT DO NOTHING on their deterministic ids, and a run is claimed by moving it from
pending to running in one UPDATE, so no call is ever made twice for the same cell.
"""

import uuid
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PageParams, keyset
from app.modules.engine.models import Experiment, ExperimentEvent, TestCaseRun
from app.modules.engine.schemas import ExperimentStatus, RunStatus
from app.modules.prompts.models import Prompt, PromptVersion


class EngineRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, row: Experiment | ExperimentEvent) -> None:
        self._session.add(row)
        await self._session.flush()

    async def experiment(self, experiment_id: uuid.UUID, project_id: uuid.UUID | None = None) -> Experiment | None:
        query = select(Experiment).where(Experiment.id == experiment_id).execution_options(populate_existing=True)
        if project_id is not None:
            query = query.where(Experiment.project_id == project_id)
        return await self._session.scalar(query)

    async def experiments(self, project_id: uuid.UUID, page: PageParams) -> list[Experiment]:
        query = keyset(select(Experiment).where(Experiment.project_id == project_id), Experiment.id, page)
        return list((await self._session.scalars(query)).all())

    async def is_running(self, experiment_id: uuid.UUID) -> bool:
        """The run's state right now (a column read, so a pause made by another request is seen, not a cached row)."""
        status = await self._session.scalar(select(Experiment.status).where(Experiment.id == experiment_id))
        return status is ExperimentStatus.RUNNING

    async def compare_and_set(
        self, experiment_id: uuid.UUID, current: ExperimentStatus, target: ExperimentStatus, values: dict[str, Any]
    ) -> bool:
        result = await self._session.execute(
            update(Experiment)
            .where(Experiment.id == experiment_id, Experiment.status == current)
            .values(status=target, **values)
        )
        return bool(getattr(result, "rowcount", 0))

    async def last_reason(self, experiment_id: uuid.UUID) -> str | None:
        query = (
            select(ExperimentEvent.reason)
            .where(ExperimentEvent.experiment_id == experiment_id)
            .order_by(ExperimentEvent.id.desc())
            .limit(1)
        )
        reason: str | None = await self._session.scalar(query)
        return reason

    async def insert_runs(self, rows: Sequence[dict[str, Any]]) -> None:
        for start in range(0, len(rows), 1000):
            batch = list(rows[start : start + 1000])
            await self._session.execute(insert(TestCaseRun).values(batch).on_conflict_do_nothing())

    async def run_ids(self, experiment_id: uuid.UUID, status: RunStatus) -> list[uuid.UUID]:
        query = select(TestCaseRun.id).where(TestCaseRun.experiment_id == experiment_id, TestCaseRun.status == status)
        return list((await self._session.scalars(query.order_by(TestCaseRun.provider, TestCaseRun.id))).all())

    async def runs(self, experiment_id: uuid.UUID, ids: Sequence[uuid.UUID] | None = None) -> list[TestCaseRun]:
        query = select(TestCaseRun).where(TestCaseRun.experiment_id == experiment_id)
        if ids is not None:
            query = query.where(TestCaseRun.id.in_(ids))
        return list((await self._session.scalars(query.execution_options(populate_existing=True))).all())

    async def run(self, experiment_id: uuid.UUID, run_id: uuid.UUID) -> TestCaseRun | None:
        query = select(TestCaseRun).where(TestCaseRun.experiment_id == experiment_id, TestCaseRun.id == run_id)
        return await self._session.scalar(query)

    async def claim(
        self, experiment_id: uuid.UUID, run_id: uuid.UUID, now: datetime, lease_until: datetime | None = None
    ) -> bool:
        result = await self._session.execute(
            update(TestCaseRun)
            .where(
                TestCaseRun.experiment_id == experiment_id,
                TestCaseRun.id == run_id,
                TestCaseRun.status == RunStatus.PENDING,
            )
            .values(status=RunStatus.RUNNING, started_at=now, lease_expires_at=lease_until)
        )
        return bool(getattr(result, "rowcount", 0))

    async def update_run(self, experiment_id: uuid.UUID, run_id: uuid.UUID, values: dict[str, Any]) -> None:
        await self._session.execute(
            update(TestCaseRun)
            .where(TestCaseRun.experiment_id == experiment_id, TestCaseRun.id == run_id)
            .values(**values)
        )

    async def set_status(
        self, experiment_id: uuid.UUID, current: RunStatus, target: RunStatus, values: dict[str, Any] | None = None
    ) -> None:
        await self._session.execute(
            update(TestCaseRun)
            .where(TestCaseRun.experiment_id == experiment_id, TestCaseRun.status == current)
            .values(status=target, **(values or {}))
        )

    async def returned_models(self, experiment_id: uuid.UUID) -> list[tuple[uuid.UUID, str | None, int]]:
        query = (
            select(TestCaseRun.model_profile_id, TestCaseRun.response_model, func.count())
            .where(TestCaseRun.experiment_id == experiment_id, TestCaseRun.status == RunStatus.SUCCEEDED)
            .group_by(TestCaseRun.model_profile_id, TestCaseRun.response_model)
        )
        return [(row[0], row[1], row[2]) for row in (await self._session.execute(query)).all()]

    async def prompt_numbers(self, version_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, int]:
        rows = await self._session.execute(
            select(PromptVersion.id, PromptVersion.version).where(PromptVersion.id.in_(set(version_ids)))
        )
        return {row[0]: row[1] for row in rows.all()}

    async def prompt_names(self, version_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, tuple[uuid.UUID, str]]:
        """For each prompt version: the prompt it belongs to and that prompt's name."""
        rows = await self._session.execute(
            select(PromptVersion.id, PromptVersion.prompt_id, Prompt.name)
            .join(Prompt, Prompt.id == PromptVersion.prompt_id)
            .where(PromptVersion.id.in_(set(version_ids)))
        )
        return {row[0]: (row[1], row[2]) for row in rows.all()}

    async def progress(self, experiment_id: uuid.UUID) -> list[tuple[uuid.UUID, str, RunStatus, int, Decimal | None]]:
        query = (
            select(
                TestCaseRun.model_profile_id,
                TestCaseRun.model,
                TestCaseRun.status,
                func.count(),
                func.sum(TestCaseRun.cost),
            )
            .where(TestCaseRun.experiment_id == experiment_id)
            .group_by(TestCaseRun.model_profile_id, TestCaseRun.model, TestCaseRun.status)
        )
        return [(m, name, s, int(n), c) for m, name, s, n, c in (await self._session.execute(query)).all()]

    async def spent(self, experiment_id: uuid.UUID) -> Decimal:
        total = await self._session.scalar(
            select(func.coalesce(func.sum(TestCaseRun.cost), 0)).where(TestCaseRun.experiment_id == experiment_id)
        )
        return Decimal(total or 0)

    async def open_count(self, experiment_id: uuid.UUID) -> int:
        count = await self._session.scalar(
            select(func.count()).where(
                TestCaseRun.experiment_id == experiment_id,
                TestCaseRun.status.in_([RunStatus.PENDING, RunStatus.RUNNING]),
            )
        )
        return int(count or 0)

    async def extend_leases(self, experiment_id: uuid.UUID, run_ids: Sequence[uuid.UUID], until: datetime) -> None:
        """The heartbeat: calls this worker is still making keep their claim."""
        await self._session.execute(
            update(TestCaseRun)
            .where(
                TestCaseRun.experiment_id == experiment_id,
                TestCaseRun.id.in_(list(run_ids)),
                TestCaseRun.status == RunStatus.RUNNING,
            )
            .values(lease_expires_at=until)
        )

    async def release_expired(self, now: datetime) -> list[uuid.UUID]:
        """Calls whose worker stopped renewing the claim go back to pending. Returns the experiments they belong to."""
        result = await self._session.execute(
            update(TestCaseRun)
            .where(
                TestCaseRun.status == RunStatus.RUNNING,
                TestCaseRun.lease_expires_at.is_not(None),
                TestCaseRun.lease_expires_at <= now,
            )
            .values(status=RunStatus.PENDING, started_at=None, lease_expires_at=None)
            .returning(TestCaseRun.experiment_id)
        )
        return sorted({row[0] for row in result.all()}, key=str)

    async def requeue_failed(self, experiment_id: uuid.UUID, error_types: Sequence[str]) -> int:
        result = await self._session.execute(
            update(TestCaseRun)
            .where(
                TestCaseRun.experiment_id == experiment_id,
                TestCaseRun.status == RunStatus.FAILED,
                TestCaseRun.error_type.in_(list(error_types)),
            )
            .values(
                status=RunStatus.PENDING,
                error_type=None,
                error_message=None,
                started_at=None,
                completed_at=None,
                lease_expires_at=None,
            )
        )
        return int(getattr(result, "rowcount", 0) or 0)

    async def running_experiments(self, status: ExperimentStatus) -> list[uuid.UUID]:
        rows = await self._session.scalars(select(Experiment.id).where(Experiment.status == status))
        return list(rows.all())

    async def mean_cost(self, experiment_id: uuid.UUID) -> Decimal | None:
        value = await self._session.scalar(
            select(func.avg(TestCaseRun.cost)).where(TestCaseRun.experiment_id == experiment_id)
        )
        return None if value is None else Decimal(value)
