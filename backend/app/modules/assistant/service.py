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
from app.core.pagination import PageParams
from app.core.security import Principal
from app.modules.assistant.models import OptimizationSession, PromptCandidate
from app.modules.assistant.quality import quality
from app.modules.assistant.repository import AssistantRepository
from app.modules.assistant.schemas import (
    CandidateOut,
    CandidateOutcome,
    CandidateRef,
    ClusterOut,
    ImprovementOut,
    ImprovementSummary,
    OptimizationStatus,
    SessionStage,
    VerdictOut,
)
from app.modules.datasets.schemas import Split
from app.modules.datasets.service import DatasetService
from app.modules.engine.domain import TERMINAL
from app.modules.engine.models import Experiment
from app.modules.engine.repository import EngineRepository
from app.modules.engine.schemas import ExperimentOrigin, SplitScope
from app.modules.engine.service import ExperimentService
from app.modules.evaluation.repository import ScoreRepository
from app.modules.evaluation.results import ResultsService
from app.modules.evaluation.schemas import JudgeChoice
from app.modules.projects.schemas import ProjectOut
from app.modules.prompts.schemas import PromptSource, PromptVersionCreate, PromptVersionOut
from app.modules.prompts.service import PromptService
from app.modules.registry.service import RegistryService

HISTORY_LIMIT = 30
IMPROVE_JOB = "assistant.improve"
RESUME_JOB = "assistant.resume"
WORKING = {SessionStage.ANALYZING, SessionStage.TESTING, SessionStage.CONFIRMING}
NOT_WORKING = "This improvement is not running."
NOT_STOPPED = "Only an improvement that was stopped or failed can be continued."
STOPPED = "Stopped. Everything done so far is kept; press Continue to carry on."
SESSION_NOT_FOUND = "This improvement session doesn't exist in this project."
EXPERIMENT_NOT_FOUND = "This experiment doesn't exist in this project."
NOT_SCORED = "Wait until this experiment has been scored."
NEEDS_BOTH_SPLITS = "Improve needs an experiment that ran on all test cases (both the optimize and holdout parts)."
NOT_MANUAL = "Start Improve from one of your own experiments, not from a candidate test."
NOT_BETTER = "Only a candidate that beat the current prompt on the holdout cases can be accepted."
ACCEPTED = "Accepted improvement: {strategy}"
TO_TEST = "Improvement to test: {strategy}"
OUTCOME_RANK = {
    CandidateOutcome.ACCEPTED: 0,
    CandidateOutcome.BETTER: 1,
    CandidateOutcome.NOT_BETTER: 2,
    CandidateOutcome.PENDING: 3,
    CandidateOutcome.REJECTED: 4,
}


class ImprovementService:
    def __init__(self, session: AsyncSession, container: Container) -> None:
        self._session = session
        self._repo = AssistantRepository(session)
        self._engine = EngineRepository(session)
        self._scores = ScoreRepository(session)
        self._datasets = DatasetService(session, container.settings)
        self._results = ResultsService.from_container(session, container)
        self._registry = RegistryService(session, container)
        self._prompts = PromptService(session, self._registry, container.settings)
        self._experiments = ExperimentService.from_container(session, container)
        self._jobs: JobQueue = container.jobs

    async def start(
        self, project: ProjectOut, experiment_id: uuid.UUID, writer: JudgeChoice | None = None
    ) -> ImprovementOut:
        experiment = await self._experiment(project.id, experiment_id)
        if experiment.origin is not ExperimentOrigin.MANUAL:
            raise ValidationFailed(NOT_MANUAL)
        if experiment.split_scope is not SplitScope.ALL:
            raise ValidationFailed(NEEDS_BOTH_SPLITS)
        if not any(r.status.value == "completed" for r in await self._scores.runs(experiment.id)):
            raise Conflict(NOT_SCORED)
        if writer is not None:  # refused here, with the registry's message, if the key or model is gone
            await self._registry.call_target(project.id, writer.credential_id, writer.model)
        row = OptimizationSession(
            project_id=project.id,
            root_prompt_version_id=experiment.prompt_version_id,
            status=OptimizationStatus.ACTIVE,
            baseline_experiment_id=experiment.id,
            stage=SessionStage.ANALYZING,
            writer=writer.model_dump(mode="json") if writer else None,
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
        candidates = [await self._candidate_out(row.project_id, c) for c in await self._repo.candidates(row.id)]
        return ImprovementOut(
            id=row.id,
            status=row.status,
            stage=SessionStage(row.stage),
            message=row.message,
            writer_model=(row.writer or {}).get("model") or (baseline.config.get("judge") or {}).get("model")
            if baseline
            else None,
            root_prompt_version_id=row.root_prompt_version_id,
            baseline_experiment_id=row.baseline_experiment_id,
            baseline_optimize_quality=await self._quality(baseline, Split.OPTIMIZE),
            baseline_holdout_quality=await self._quality(baseline, Split.HOLDOUT),
            clusters=[ClusterOut.model_validate(c) for c in clusters],
            candidates=candidates,
            created_at=row.created_at,
        )

    async def stop(self, project: ProjectOut, session_id: uuid.UUID) -> ImprovementOut:
        """Stop where it is: tests that are running are cancelled (their finished answers are kept) and the
        session waits for Continue. Nothing is deleted."""
        row = await self._session_row(project.id, session_id)
        if SessionStage(row.stage) not in WORKING:
            raise Conflict(NOT_WORKING)
        await self._repo.update_session(row.id, {"stage": SessionStage.STOPPED, "message": STOPPED})
        await self._session.commit()
        for candidate in await self._repo.candidates(row.id):
            for experiment_id in (candidate.optimize_experiment_id, candidate.holdout_experiment_id):
                experiment = await self._engine.experiment(experiment_id) if experiment_id else None
                if experiment is not None and experiment.status not in TERMINAL:  # finished ones keep their result
                    await self._experiments.stop(experiment, "Stopped from Improve.")
        return await self.get(project.id, row.id)

    async def resume(self, project: ProjectOut, session_id: uuid.UUID) -> ImprovementOut:
        """Carry on from where it stopped or failed: write the improvements again if none were written,
        otherwise test the candidates that were never tested and go on from there."""
        row = await self._session_row(project.id, session_id)
        if SessionStage(row.stage) not in (SessionStage.STOPPED, SessionStage.FAILED):
            raise Conflict(NOT_STOPPED)
        started = bool(await self._repo.candidates(row.id))
        stage = SessionStage.TESTING if started else SessionStage.ANALYZING
        if not await self._repo.update_session(row.id, {"stage": stage, "message": None}, stage_was=row.stage):
            raise Conflict(NOT_STOPPED)
        await self._session.commit()
        self._jobs.enqueue(RESUME_JOB if started else IMPROVE_JOB, session_id=str(row.id))
        return await self.get(project.id, row.id)

    async def history(self, project: ProjectOut) -> list[ImprovementSummary]:
        """The project's earlier improvements, newest first, each with its best candidate."""
        out = []
        for row in await self._repo.sessions(project.id, HISTORY_LIMIT):
            candidates = await self._repo.candidates(row.id)
            best = min(candidates, key=lambda c: OUTCOME_RANK[CandidateOutcome(c.outcome)], default=None)
            out.append(
                ImprovementSummary(
                    id=row.id,
                    stage=SessionStage(row.stage),
                    message=row.message,
                    baseline_experiment_id=row.baseline_experiment_id,
                    created_at=row.created_at,
                    candidate_count=len(candidates),
                    best_strategy=best.strategy if best else None,
                    best_outcome=CandidateOutcome(best.outcome) if best else None,
                )
            )
        return out

    async def candidate_for(self, project: ProjectOut, experiment_id: uuid.UUID) -> CandidateRef | None:
        """The candidate a finished experiment was testing (an Improve test), or None for your own runs."""
        candidate = await self._repo.candidate_for_experiment(experiment_id)
        if candidate is None:
            return None
        row = await self._repo.session(candidate.session_id, project.id)
        if row is None:
            return None
        return CandidateRef(
            session_id=row.id,
            candidate_id=candidate.id,
            strategy=candidate.strategy,
            outcome=CandidateOutcome(candidate.outcome),
        )

    async def accept(
        self,
        project: ProjectOut,
        principal: Principal,
        session_id: uuid.UUID,
        candidate_id: uuid.UUID,
        run: bool = False,
    ) -> ImprovementOut:
        row = await self._session_row(project.id, session_id)
        candidate = next((c for c in await self._repo.candidates(row.id) if c.id == candidate_id), None)
        if candidate is None:
            raise NotFound(SESSION_NOT_FOUND)
        if candidate.outcome is not CandidateOutcome.BETTER:
            raise Conflict(NOT_BETTER)
        version = await self._save_version(project, principal, candidate, ACCEPTED)
        await self._repo.update_candidate(candidate.id, {"outcome": CandidateOutcome.ACCEPTED})
        await self._repo.update_session(row.id, {"status": OptimizationStatus.CLOSED})
        return await self._done(project, principal, row, version.id if run else None)

    async def save_candidate(
        self,
        project: ProjectOut,
        principal: Principal,
        session_id: uuid.UUID,
        candidate_id: uuid.UUID,
        run: bool = False,
    ) -> ImprovementOut:
        """Save any candidate as a normal prompt version so it can be tested on the Run step, proven better or
        not (with `run`, test it on all test cases right away). The session and the candidate's result are left
        as they are."""
        row = await self._session_row(project.id, session_id)
        candidate = next((c for c in await self._repo.candidates(row.id) if c.id == candidate_id), None)
        if candidate is None:
            raise NotFound(SESSION_NOT_FOUND)
        version = await self._save_version(project, principal, candidate, TO_TEST)
        return await self._done(project, principal, row, version.id if run else None)

    async def _done(
        self, project: ProjectOut, principal: Principal, row: OptimizationSession, test_version: uuid.UUID | None
    ) -> ImprovementOut:
        """The improvement as it now stands; when a version is given, the baseline's test is run again on it (all
        test cases, the same models and settings) and the new experiment's id is returned."""
        started = None
        if test_version is not None and row.baseline_experiment_id is not None:
            started = (await self._experiments.rerun(project, principal, row.baseline_experiment_id, test_version)).id
        out = await self.get(project.id, row.id)
        return out.model_copy(update={"started_experiment_id": started})

    async def _save_version(
        self, project: ProjectOut, principal: Principal, candidate: PromptCandidate, reason: str
    ) -> PromptVersionOut:
        """The candidate as a saved version. If a saved version already has exactly its prompt, that one is used, so
        pressing the button twice does not make two versions."""
        proposed = await self._prompts.get_version(project.id, candidate.prompt_version_id)
        base = await self._prompts.get_version(project.id, candidate.base_prompt_version_id)
        saved = await self._prompts.list_versions(project, base.prompt_id, PageParams(limit=200, cursor=None))
        same = next(
            (
                v
                for v in saved.items
                if v.system_template == proposed.system_template and v.user_template == proposed.user_template
            ),
            None,
        )
        if same is not None:
            return same
        body = PromptVersionCreate(
            system_template=proposed.system_template,
            user_template=proposed.user_template,
            default_params=base.default_params,
            change_reason=reason.format(strategy=candidate.strategy),
            parent_version_id=base.id,
        )
        return await self._prompts.save_version(
            project.id, principal, base.prompt_id, body, source=PromptSource.ASSISTANT
        )

    async def _candidate_out(self, project_id: uuid.UUID, c: PromptCandidate) -> CandidateOut:
        optimize = await self._engine.experiment(c.optimize_experiment_id) if c.optimize_experiment_id else None
        holdout = await self._engine.experiment(c.holdout_experiment_id) if c.holdout_experiment_id else None
        version = await self._prompts.get_version(project_id, c.prompt_version_id)
        return CandidateOut(
            **{name: getattr(c, name) for name in CandidateOut.model_fields if name != "verdict" and hasattr(c, name)},
            system_template=version.system_template,
            user_template=version.user_template,
            optimize_quality=await self._quality(optimize, Split.OPTIMIZE),
            holdout_quality=await self._quality(holdout, Split.HOLDOUT),
            verdict=VerdictOut.model_validate(c.verdict) if c.verdict else None,
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
