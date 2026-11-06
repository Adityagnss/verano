"""
The lease sweeper (ADR 0037): what makes "a worker died" harmless.

Every piece of work a worker holds carries a lease that a heartbeat keeps renewing. This runs on a timer (a Celery
beat task). Whatever has a lease that ran out belonged to a worker that is gone, so it goes back to pending and the
job is queued again:

- calls (`test_case_runs`) that were running go back to pending and their run's pending calls are queued;
- a run whose calls all finished but whose worker died before moving it on is moved on to scoring;
- scoring passes go back to pending and are queued again (answers already scored are skipped);
- generations that were running are queued again (they are idempotent);
- security packs that were being written are queued again;
- improvements that were analysing are queued again.
Nothing stays "running" for ever, and a call that finished is never repeated.
"""

import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.jobs import JobQueue
from app.core.security import utcnow
from app.modules.assistant.models import OptimizationSession
from app.modules.assistant.schemas import SessionStage
from app.modules.datasets.models import Dataset, DatasetVersion
from app.modules.engine.domain import chunks
from app.modules.engine.repository import EngineRepository
from app.modules.engine.schemas import ExperimentStatus, RunStatus
from app.modules.evaluation.repository import ScoreRepository
from app.modules.security.models import SecurityPack

log = logging.getLogger(__name__)
RUN_CHUNK_JOB = "engine.run_chunk"
SCORE_JOB = "evaluation.score_experiment"
GENERATE_JOB = "generator.generate"
PACK_JOB = "security.generate"
IMPROVE_JOB = "assistant.improve"


@dataclass
class SweepResult:
    calls: int = 0
    runs_finished: int = 0
    scoring_passes: int = 0
    generations: int = 0
    packs: int = 0
    improvements: int = 0

    @property
    def total(self) -> int:
        return self.calls + self.runs_finished + self.scoring_passes + self.generations + self.packs + self.improvements


class LeaseSweeper:
    def __init__(self, session: AsyncSession, settings: Settings, jobs: JobQueue) -> None:
        self._session = session
        self._settings = settings
        self._jobs = jobs
        self._engine = EngineRepository(session)
        self._scores = ScoreRepository(session)
        self._pending_jobs: list[tuple[str, dict[str, object]]] = []

    async def sweep(self) -> SweepResult:
        now = utcnow()
        result = SweepResult()
        await self._calls(now, result)
        await self._finished_runs(result)
        await self._scoring(now, result)
        await self._generations(now, result)
        await self._packs(now, result)
        await self._improvements(now, result)
        await self._session.commit()
        # jobs are queued only after the changes are saved, so a job never starts before its row is pending
        for name, kwargs in self._pending_jobs:
            self._jobs.enqueue(name, **kwargs)
        if result.total:
            log.warning("lease sweeper returned work from dead workers: %s", result)
        return result

    def _queue(self, name: str, **kwargs: object) -> None:
        self._pending_jobs.append((name, kwargs))

    async def _calls(self, now: datetime, result: SweepResult) -> None:
        released = await self._engine.release_expired(now)
        for experiment_id in released:
            experiment = await self._engine.experiment(experiment_id)
            pending = await self._engine.run_ids(experiment_id, RunStatus.PENDING)
            result.calls += len(pending)
            if experiment is None:
                continue
            if experiment.status is ExperimentStatus.RUNNING:
                for ids in chunks(pending, self._settings.engine_chunk_size):
                    self._queue(RUN_CHUNK_JOB, experiment_id=str(experiment_id), run_ids=[str(i) for i in ids])
            elif experiment.status in (ExperimentStatus.CANCELLED, ExperimentStatus.FAILED):
                await self._engine.set_status(experiment_id, RunStatus.PENDING, RunStatus.SKIPPED)

    async def _finished_runs(self, result: SweepResult) -> None:
        """A run with nothing open that is still "running": its worker died after the last call was saved."""
        for experiment_id in await self._engine.running_experiments(ExperimentStatus.RUNNING):
            if await self._engine.open_count(experiment_id):
                continue
            moved = await self._engine.compare_and_set(
                experiment_id, ExperimentStatus.RUNNING, ExperimentStatus.EVALUATING, {}
            )
            if moved:
                result.runs_finished += 1
                self._queue(SCORE_JOB, experiment_id=str(experiment_id))

    async def _scoring(self, now: datetime, result: SweepResult) -> None:
        for run_id, experiment_id, trigger in await self._scores.release_expired_runs(now):
            result.scoring_passes += 1
            self._queue(SCORE_JOB, experiment_id=str(experiment_id), trigger=trigger, evaluation_run_id=str(run_id))

    async def _generations(self, now: datetime, result: SweepResult) -> None:
        query = (
            select(DatasetVersion.id, Dataset.project_id, DatasetVersion.generation)
            .join(Dataset, Dataset.id == DatasetVersion.dataset_id)
            .where(
                DatasetVersion.lease_expires_at.is_not(None),
                DatasetVersion.lease_expires_at <= now,
            )
        )
        for version_id, project_id, generation in (await self._session.execute(query)).all():
            await self._session.execute(
                update(DatasetVersion).where(DatasetVersion.id == version_id).values(lease_expires_at=None)
            )
            if (generation or {}).get("status") != "running":
                continue
            result.generations += 1
            self._queue(
                GENERATE_JOB,
                project_id=str(project_id),
                version_id=str(version_id),
                regenerate=(generation or {}).get("regenerate"),
            )

    async def _packs(self, now: datetime, result: SweepResult) -> None:
        query = select(SecurityPack.id).where(
            SecurityPack.status == "generating",
            SecurityPack.lease_expires_at.is_not(None),
            SecurityPack.lease_expires_at <= now,
        )
        for pack_id in (await self._session.scalars(query)).all():
            await self._session.execute(
                update(SecurityPack).where(SecurityPack.id == pack_id).values(lease_expires_at=None)
            )
            result.packs += 1
            self._queue(PACK_JOB, pack_id=str(pack_id))

    async def _improvements(self, now: datetime, result: SweepResult) -> None:
        query = select(OptimizationSession.id).where(
            OptimizationSession.stage == SessionStage.ANALYZING.value,
            OptimizationSession.lease_expires_at.is_not(None),
            OptimizationSession.lease_expires_at <= now,
        )
        for session_id in (await self._session.scalars(query)).all():
            await self._session.execute(
                update(OptimizationSession).where(OptimizationSession.id == session_id).values(lease_expires_at=None)
            )
            result.improvements += 1
            self._queue(IMPROVE_JOB, session_id=str(session_id))
