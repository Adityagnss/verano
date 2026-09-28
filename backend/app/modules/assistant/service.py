"""
Improve use cases, request side (DEVELOPMENT.md 5.2-5.4): start an improvement session from
a scored experiment, read it (failure clusters, candidates with their diffs and scores, the
holdout comparison), and accept the winning candidate as the prompt's new version.

The work itself runs as background jobs (`pipeline.py`). A candidate can only be accepted
when it beat the current prompt on the holdout cases; accepting saves a new, normal prompt
version (source `assistant`) with the candidate's templates, and closes the session.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.container import Container
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.jobs import JobQueue
from app.core.security import Principal
from app.modules.assistant.models import OptimizationSession, PromptCandidate
from app.modules.assistant.quality import quality
from app.modules.assistant.repository import AssistantRepository
from app.modules.assistant.schemas import (
    CandidateOut,
    CandidateOutcome,
    ClusterOut,
    ImprovementOut,
    OptimizationStatus,
    SessionStage,
)
from app.modules.datasets.schemas import Split
from app.modules.datasets.service import DatasetService
from app.modules.engine.models import Experiment
from app.modules.engine.repository import EngineRepository
from app.modules.engine.schemas import ExperimentOrigin, SplitScope
from app.modules.evaluation.repository import ScoreRepository
from app.modules.evaluation.results import ResultsService
from app.modules.projects.schemas import ProjectOut
from app.modules.prompts.schemas import PromptSource, PromptVersionCreate
from app.modules.prompts.service import PromptService
from app.modules.registry.service import RegistryService

IMPROVE_JOB = "assistant.improve"
SESSION_NOT_FOUND = "This improvement session doesn't exist in this project."
EXPERIMENT_NOT_FOUND = "This experiment doesn't exist in this project."
NOT_SCORED = "Wait until this experiment has been scored."
NEEDS_BOTH_SPLITS = "Improve needs an experiment that ran on all test cases (both the optimize and holdout parts)."
NOT_MANUAL = "Start Improve from one of your own experiments, not from a candidate test."
NOT_BETTER = "Only a candidate that beat the current prompt on the holdout cases can be accepted."
ACCEPTED = "Accepted improvement: {strategy}"


class ImprovementService:
    def __init__(self, session: AsyncSession, container: Container) -> None:
        self._session = session
        self._repo = AssistantRepository(session)
        self._engine = EngineRepository(session)
        self._scores = ScoreRepository(session)
        self._datasets = DatasetService(session, container.settings)
        self._results = ResultsService.from_container(session, container)
        self._prompts = PromptService(session, RegistryService(session, container), container.settings)
        self._jobs: JobQueue = container.jobs

    async def start(self, project: ProjectOut, experiment_id: uuid.UUID) -> ImprovementOut:
        experiment = await self._experiment(project.id, experiment_id)
        if experiment.origin is not ExperimentOrigin.MANUAL:
            raise ValidationFailed(NOT_MANUAL)
        if experiment.split_scope is not SplitScope.ALL:
            raise ValidationFailed(NEEDS_BOTH_SPLITS)
        if not any(r.status.value == "completed" for r in await self._scores.runs(experiment.id)):
            raise Conflict(NOT_SCORED)
        row = OptimizationSession(
            project_id=project.id,
            root_prompt_version_id=experiment.prompt_version_id,
            status=OptimizationStatus.ACTIVE,
            baseline_experiment_id=experiment.id,
            stage=SessionStage.ANALYZING,
        )
        await self._repo.add(row)
        await self._session.commit()
        self._jobs.enqueue(IMPROVE_JOB, session_id=str(row.id))
        return await self.get(project.id, row.id)

    async def latest(self, project: ProjectOut, experiment_id: uuid.UUID) -> ImprovementOut | None:
        row = await self._repo.latest_for(project.id, experiment_id)
        return await self.get(project.id, row.id) if row else None

    async def get(self, project_id: uuid.UUID, session_id: uuid.UUID) -> ImprovementOut:
        row = await self._session_row(project_id, session_id)
        baseline = await self._engine.experiment(row.baseline_experiment_id) if row.baseline_experiment_id else None
        runs = await self._scores.runs(baseline.id) if baseline else []
        scored = next((r for r in runs if r.status.value == "completed"), None)
        clusters = await self._repo.clusters(scored.id) if scored else []
        candidates = [await self._candidate_out(c) for c in await self._repo.candidates(row.id)]
        return ImprovementOut(
            id=row.id,
            status=row.status,
            stage=SessionStage(row.stage),
            message=row.message,
            root_prompt_version_id=row.root_prompt_version_id,
            baseline_experiment_id=row.baseline_experiment_id,
            baseline_optimize_quality=await self._quality(baseline, Split.OPTIMIZE),
            baseline_holdout_quality=await self._quality(baseline, Split.HOLDOUT),
            clusters=[ClusterOut.model_validate(c) for c in clusters],
            candidates=candidates,
            created_at=row.created_at,
        )

    async def accept(
        self, project: ProjectOut, principal: Principal, session_id: uuid.UUID, candidate_id: uuid.UUID
    ) -> ImprovementOut:
        row = await self._session_row(project.id, session_id)
        candidate = next((c for c in await self._repo.candidates(row.id) if c.id == candidate_id), None)
        if candidate is None:
            raise NotFound(SESSION_NOT_FOUND)
        if candidate.outcome is not CandidateOutcome.BETTER:
            raise Conflict(NOT_BETTER)
        proposed = await self._prompts.get_version(project.id, candidate.prompt_version_id)
        base = await self._prompts.get_version(project.id, candidate.base_prompt_version_id)
        body = PromptVersionCreate(
            system_template=proposed.system_template,
            user_template=proposed.user_template,
            default_params=base.default_params,
            change_reason=ACCEPTED.format(strategy=candidate.strategy),
            parent_version_id=base.id,
        )
        await self._prompts.save_version(project.id, principal, base.prompt_id, body, source=PromptSource.ASSISTANT)
        await self._repo.update_candidate(candidate.id, {"outcome": CandidateOutcome.ACCEPTED})
        await self._repo.update_session(row.id, {"status": OptimizationStatus.CLOSED})
        return await self.get(project.id, row.id)

    async def _candidate_out(self, c: PromptCandidate) -> CandidateOut:
        optimize = await self._engine.experiment(c.optimize_experiment_id) if c.optimize_experiment_id else None
        holdout = await self._engine.experiment(c.holdout_experiment_id) if c.holdout_experiment_id else None
        return CandidateOut(
            **{name: getattr(c, name) for name in CandidateOut.model_fields if hasattr(c, name)},
            optimize_quality=await self._quality(optimize, Split.OPTIMIZE),
            holdout_quality=await self._quality(holdout, Split.HOLDOUT),
        )

    async def _quality(self, experiment: Experiment | None, split: Split) -> float | None:
        return await quality(self._results, self._datasets, experiment, split) if experiment else None

    async def _session_row(self, project_id: uuid.UUID, session_id: uuid.UUID) -> OptimizationSession:
        row = await self._repo.session(session_id, project_id)
        if row is None:
            raise NotFound(SESSION_NOT_FOUND)
        return row

    async def _experiment(self, project_id: uuid.UUID, experiment_id: uuid.UUID) -> Experiment:
        row = await self._engine.experiment(experiment_id, project_id)
        if row is None:
            raise NotFound(EXPERIMENT_NOT_FOUND)
        return row
