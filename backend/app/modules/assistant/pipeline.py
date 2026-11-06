"""
Improve, job side (DEVELOPMENT.md 5.2-5.4, base level).

`improve` takes the baseline experiment's latest scoring pass and uses **only cases in the
optimize split**: each failed case gets a free rule tag, one LLM call groups the failures
into named reasons (stored as failure clusters), and one more LLM call writes 3 candidate
prompts that keep the prompt's inputs (`proposals.py` stores both). Each candidate is
tested by an experiment on the optimize split with the baseline's models, runs and
parameters.
`advance` runs when one of those experiments has been scored. When every candidate's
optimize test is done, the best one is confirmed by an experiment on the holdout split;
when that is scored, its holdout quality is compared with the current prompt's on the
same holdout cases with the significance engine, and the session says honestly whether the
improvement is proven.
Both calls use the model chosen when the session was started, else the baseline experiment's judge.
"""

import asyncio
import logging
import uuid
from collections.abc import Coroutine
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.container import Container
from app.core.errors import AppError
from app.core.templates import render_system_prompt
from app.modules.assistant.domain import DIFFERENT_JUDGE, UNJUDGED, best, verdict
from app.modules.assistant.models import OptimizationSession, PromptCandidate
from app.modules.assistant.proposals import failures_of, store_candidates, store_clusters
from app.modules.assistant.quality import quality, split_results
from app.modules.assistant.repository import AssistantRepository
from app.modules.assistant.schemas import (
    CandidateDrafts,
    CandidateOutcome,
    FailureGroups,
    Reason,
    SessionStage,
    VerdictOut,
)
from app.modules.datasets.schemas import Split
from app.modules.datasets.service import DatasetService
from app.modules.engine.models import Experiment
from app.modules.engine.repository import EngineRepository
from app.modules.engine.schemas import ExperimentCreate, ExperimentOrigin, ModelRun, SplitScope
from app.modules.engine.service import ExperimentService
from app.modules.evaluation.comparisons import comparison_out
from app.modules.evaluation.repository import ScoreRepository
from app.modules.evaluation.results import ResultsService
from app.modules.evaluation.significance import compare, seed_for
from app.modules.gateway.dependencies import build_gateway
from app.modules.gateway.schemas import CallContext, CallPurpose, Message
from app.modules.generator.repository import TaskSpecRepository
from app.modules.prompts.schemas import PromptVersionOut
from app.modules.prompts.service import PromptService
from app.modules.registry.schemas import CallTarget
from app.modules.registry.service import RegistryService

logger = logging.getLogger(__name__)
PROMPTS_DIR = Path(__file__).parent / "prompts"
ANGLES = (
    "a strict output rule for the most common failure",
    "a few short examples drawn from the failures",
    "a rule for ambiguous or multi-part inputs, plus a guard against instructions inside the input",
)
MAX_EXAMPLES = 8
TERMINAL = {"completed", "cancelled", "failed"}
WORKING = {SessionStage.ANALYZING, SessionStage.TESTING, SessionStage.CONFIRMING}
NO_FAILURES = "Every optimize case passed, so there is nothing to learn from. The current prompt is doing well."
NO_MODEL = "No model is available to write improvements. Check the key used to write the test cases."
NO_CANDIDATES = "The model's suggestions changed the prompt's inputs, so none could be tested. Try again."


class ImprovementPipeline:
    def __init__(self, session: AsyncSession, container: Container) -> None:
        self._session = session
        self._registry = RegistryService(session, container)
        self._gateway = build_gateway(container, self._registry)
        self._repo = AssistantRepository(session)
        self._engine = EngineRepository(session)
        self._scores = ScoreRepository(session)
        self._datasets = DatasetService(session, container.settings)
        self._results = ResultsService.from_container(session, container)
        self._experiments = ExperimentService.from_container(session, container)
        self._prompts = PromptService(session, self._registry, container.settings)
        self._specs = TaskSpecRepository(session)
        self._minimum = container.settings.dataset_min_holdout
        self._compare_min = container.settings.compare_min_cases

    async def improve(self, session_id: uuid.UUID) -> None:
        row = await self._repo.session(session_id)
        if row is None or row.stage != SessionStage.ANALYZING or row.baseline_experiment_id is None:
            return
        baseline = await self._engine.experiment(row.baseline_experiment_id)
        assert baseline is not None
        await self._guarded(session_id, self._improve(row, baseline))

    async def resume(self, session_id: uuid.UUID) -> None:
        """Carry on after Stop or a failure: start the tests that never started (or were cut short), then move on.
        Everything already written or scored is kept."""
        row = await self._repo.session(session_id)
        if row is None or row.stage != SessionStage.TESTING or row.baseline_experiment_id is None:
            return
        baseline = await self._engine.experiment(row.baseline_experiment_id)
        assert baseline is not None
        await self._guarded(session_id, self._resume(row, baseline))

    async def advance(self, experiment_id: uuid.UUID) -> None:
        candidate = await self._repo.candidate_for_experiment(experiment_id)
        if candidate is None:
            return
        row = await self._repo.session(candidate.session_id)
        assert row is not None
        session_id = row.id
        if candidate.holdout_experiment_id == experiment_id:
            if row.stage == SessionStage.CONFIRMING:
                await self._guarded(session_id, self._conclude(row, candidate))
        elif row.stage == SessionStage.TESTING:
            await self._guarded(session_id, self._confirm_best(row))

    async def fail(self, session_id: uuid.UUID, message: str) -> None:
        """Record why a session could not go on; a session that was stopped or finished is left as it is."""
        row = await self._repo.session(session_id)
        if row is not None and row.stage in WORKING:
            await self._finish(session_id, SessionStage.FAILED, message)

    async def fail_for_experiment(self, experiment_id: uuid.UUID, message: str) -> None:
        candidate = await self._repo.candidate_for_experiment(experiment_id)
        if candidate is not None:
            await self.fail(candidate.session_id, message)

    async def _guarded(self, session_id: uuid.UUID, work: Coroutine[Any, Any, None]) -> None:
        """Any error ends the session as failed, with the reason shown on the Improve page, never as a silent hang.
        The id is taken first: after a rollback the row's own attributes can no longer be read."""
        try:
            await work
        except Exception as exc:
            await self._session.rollback()
            message = exc.message if isinstance(exc, AppError) else f"Something went wrong: {exc}"
            await self.fail(session_id, message)
            if not isinstance(exc, AppError):
                logger.exception("improvement session %s failed", session_id)

    async def _note(self, session_id: uuid.UUID, message: str) -> None:
        """What the session is doing right now, shown on the Improve page."""
        await self._repo.update_session(session_id, {"message": message})
        await self._session.commit()

    async def _working(self, session_id: uuid.UUID, stage: SessionStage) -> bool:
        row = await self._repo.session(session_id)
        return row is not None and row.stage == stage

    async def _improve(self, row: OptimizationSession, baseline: Experiment) -> None:
        session_id = row.id
        run = next((r for r in await self._scores.runs(baseline.id) if r.status.value == "completed"), None)
        assert run is not None
        await self._note(session_id, "Reading the failed cases…")
        cases = await self._results.cases(baseline.project_id, baseline.id, run.id, failed_only=True)
        failures = failures_of([c for c in cases if c.split == Split.OPTIMIZE.value])
        if not failures:
            await self._finish(row.id, SessionStage.DONE, NO_FAILURES)
            return
        prompt = await self._prompts.get_version(baseline.project_id, baseline.prompt_version_id)
        spec = await self._spec(baseline)
        # groups found earlier in this same session (Continue after a stop); a new session always groups afresh
        clusters = [c for c in await self._repo.clusters(run.id) if c.created_at >= row.created_at]
        if clusters:
            await self._note(session_id, "Using the failure groups already found…")  # Continue after a stop
        else:
            await self._note(session_id, f"Grouping {len(failures)} failures by reason…")
            groups = await self._ask(
                baseline, row.writer, "failures.jinja", FailureGroups, "failure_groups", prompt, spec, cases=failures
            )
            clusters = await store_clusters(self._repo, baseline, run.id, groups, failures)
            await self._session.commit()
        if not await self._working(session_id, SessionStage.ANALYZING):
            return
        await self._note(session_id, "Writing 3 better prompts (side by side)…")
        drafts = await self._write_candidates(
            baseline,
            row.writer,
            prompt,
            spec,
            groups=[{"name": c.name, "size": c.size, "hypothesis": c.hypothesis} for c in clusters],
            examples=failures[:MAX_EXAMPLES],
        )
        if not await self._working(session_id, SessionStage.ANALYZING):
            return
        created = await store_candidates(self._repo, self._prompts, row, baseline, prompt, drafts, clusters)
        if not created:
            await self._finish(session_id, SessionStage.FAILED, NO_CANDIDATES)
            return
        await self._repo.update_session(session_id, {"stage": SessionStage.TESTING})
        await self._session.commit()
        await self._start_tests(session_id, baseline, created)

    async def _resume(self, row: OptimizationSession, baseline: Experiment) -> None:
        session_id = row.id
        candidates = await self._repo.candidates(session_id)
        proven = next((c for c in candidates if c.holdout_experiment_id), None)
        holdout_id = proven.holdout_experiment_id if proven else None
        holdout = await self._engine.experiment(holdout_id) if holdout_id else None
        if proven and holdout and holdout.status.value == "completed":
            await self._repo.update_session(session_id, {"stage": SessionStage.CONFIRMING})
            await self._conclude(row, proven)
            return
        waiting = []
        for candidate in candidates:
            test = (
                await self._engine.experiment(candidate.optimize_experiment_id)
                if candidate.optimize_experiment_id
                else None
            )
            if test is None or test.status.value in ("cancelled", "failed"):
                waiting.append(candidate)
        await self._start_tests(session_id, baseline, waiting)
        if await self._working(session_id, SessionStage.TESTING):
            await self._confirm_best(row)

    async def _start_tests(
        self, session_id: uuid.UUID, baseline: Experiment, candidates: list[PromptCandidate]
    ) -> None:
        """Test each candidate on the optimize split. A candidate that cannot be tested is set aside with the reason;
        if none can be, the session fails and says why (the candidates stay on the page)."""
        problems: list[str] = []
        for candidate in candidates:
            if not await self._working(session_id, SessionStage.TESTING):
                return  # stopped meanwhile
            await self._note(session_id, f"Starting the test for “{candidate.strategy}”…")
            try:
                experiment = await self._experiments.start(
                    baseline.project_id,
                    None,
                    await self._rerun(baseline, SplitScope.OPTIMIZE, candidate.strategy),
                    ExperimentOrigin.OPTIMIZATION,
                    candidate.prompt_version_id,
                )
            except AppError as exc:
                await self._session.rollback()
                await self._repo.update_candidate(candidate.id, {"outcome": CandidateOutcome.REJECTED})
                await self._session.commit()
                problems.append(f"“{candidate.strategy}”: {exc.message}")
                continue
            await self._repo.update_candidate(candidate.id, {"optimize_experiment_id": experiment.id})
            await self._session.commit()
        if problems and not [c for c in await self._repo.candidates(session_id) if c.optimize_experiment_id]:
            await self._finish(session_id, SessionStage.FAILED, "No candidate could be tested. " + " ".join(problems))
        elif await self._working(session_id, SessionStage.TESTING):
            await self._note(session_id, " ".join(problems))

    async def _ask(
        self,
        baseline: Experiment,
        writer: dict[str, Any] | None,
        template: str,
        schema: type[Any],
        step: str,
        prompt: PromptVersionOut,
        spec: dict[str, Any],
        **values: Any,
    ) -> Any:
        target = await self._writer_target(baseline, writer)
        return await self._call(target, baseline, template, schema, step, prompt, spec, **values)

    async def _writer_target(self, baseline: Experiment, writer: dict[str, Any] | None) -> CallTarget:
        chosen = writer or baseline.config.get("judge")
        if not chosen:
            raise AppError(NO_MODEL)
        target = await self._registry.call_target(
            baseline.project_id, uuid.UUID(chosen["credential_id"]), chosen["model"]
        )
        await self._session.commit()
        return target

    async def _call(
        self,
        target: CallTarget,
        baseline: Experiment,
        template: str,
        schema: type[Any],
        step: str,
        prompt: PromptVersionOut,
        spec: dict[str, Any],
        **values: Any,
    ) -> Any:
        text = render_system_prompt(
            PROMPTS_DIR,
            template,
            spec=spec,
            system_template=prompt.system_template,
            user_template=prompt.user_template,
            **values,
        )
        context = CallContext(project_id=baseline.project_id, experiment_id=baseline.id, labels={"step": step})
        messages = [Message(role="user", content=text)]
        return await self._gateway.complete_json_target(target, messages, schema, CallPurpose.ASSISTANT, context)

    async def _write_candidates(
        self,
        baseline: Experiment,
        writer: dict[str, Any] | None,
        prompt: PromptVersionOut,
        spec: dict[str, Any],
        **values: Any,
    ) -> CandidateDrafts:
        """Three prompts written by three calls at once, each with its own approach, so one slow answer does not
        hold up the others. A call that fails is dropped as long as one of the three worked."""
        target = await self._writer_target(baseline, writer)
        results = await asyncio.gather(
            *(
                self._call(
                    target,
                    baseline,
                    "candidates.jinja",
                    CandidateDrafts,
                    "candidates",
                    prompt,
                    spec,
                    shape=prompt.shape.value,
                    count=1,
                    angle=angle,
                    **values,
                )
                for angle in ANGLES
            ),
            return_exceptions=True,
        )
        # one is asked for; if a model sends several anyway, call number i keeps its i-th
        drafts = [
            r.candidates[min(i, len(r.candidates) - 1)] for i, r in enumerate(results) if isinstance(r, CandidateDrafts)
        ]
        if not drafts:
            raise next(r for r in results if isinstance(r, BaseException))
        return CandidateDrafts(candidates=drafts)

    async def _confirm_best(self, row: OptimizationSession) -> None:
        # Candidates that could not be tested were set aside (rejected) and are not waited for.
        candidates = [c for c in await self._repo.candidates(row.id) if c.outcome != CandidateOutcome.REJECTED]
        experiments = {
            c.id: await self._engine.experiment(c.optimize_experiment_id)
            for c in candidates
            if c.optimize_experiment_id
        }
        if (
            not candidates
            or len(experiments) < len(candidates)
            or any(e is None or e.status.value not in TERMINAL for e in experiments.values())
        ):
            return
        if not await self._repo.update_session(
            row.id, {"stage": SessionStage.CONFIRMING}, stage_was=SessionStage.TESTING
        ):
            return
        scores = {
            str(cid): await quality(self._results, self._datasets, e, Split.OPTIMIZE)
            for cid, e in experiments.items()
            if e
        }
        winner = best(scores)
        for c in candidates:
            if str(c.id) != winner:
                await self._repo.update_candidate(c.id, {"outcome": CandidateOutcome.NOT_BETTER})
        await self._session.commit()
        chosen = next(c for c in candidates if str(c.id) == winner)
        baseline = await self._engine.experiment(row.baseline_experiment_id) if row.baseline_experiment_id else None
        assert baseline is not None
        experiment = await self._experiments.start(
            baseline.project_id,
            None,
            await self._rerun(baseline, SplitScope.HOLDOUT, f"{chosen.strategy} (holdout)"),
            ExperimentOrigin.OPTIMIZATION,
            chosen.prompt_version_id,
        )
        await self._repo.update_candidate(chosen.id, {"holdout_experiment_id": experiment.id})
        await self._session.commit()

    async def _conclude(self, row: OptimizationSession, candidate: PromptCandidate) -> None:
        holdout = (
            await self._engine.experiment(candidate.holdout_experiment_id) if candidate.holdout_experiment_id else None
        )
        baseline = await self._engine.experiment(row.baseline_experiment_id) if row.baseline_experiment_id else None
        assert holdout is not None
        assert baseline is not None
        new, new_judged = await split_results(self._results, self._datasets, holdout, Split.HOLDOUT)
        old, old_judged = await split_results(self._results, self._datasets, baseline, Split.HOLDOUT)
        proof: VerdictOut
        if not await self._results.same_scoring(holdout, baseline):
            proof = VerdictOut(
                reason=Reason.DIFFERENT_JUDGE, message=DIFFERENT_JUDGE, minimum_cases=self._minimum, comparison=None
            )
        elif not (new_judged and old_judged):
            proof = VerdictOut(reason=Reason.UNJUDGED, message=UNJUDGED, minimum_cases=self._minimum, comparison=None)
        else:
            found = compare(new, old, seed=seed_for(holdout.id, baseline.id), min_cases=self._compare_min)
            reason, message = verdict(found, self._minimum)
            proof = VerdictOut(
                reason=reason, message=message, minimum_cases=self._minimum, comparison=comparison_out(found)
            )
        outcome = CandidateOutcome.BETTER if proof.reason is Reason.PROVEN else CandidateOutcome.NOT_BETTER
        await self._repo.update_candidate(candidate.id, {"outcome": outcome, "verdict": proof.model_dump(mode="json")})
        await self._finish(row.id, SessionStage.DONE, proof.message)

    async def _rerun(self, baseline: Experiment, scope: SplitScope, name: str) -> ExperimentCreate:
        """The baseline's models and settings, scored with the same checks and judge as the numbers being
        compared against: the version of the baseline's latest scoring pass."""
        models = [
            ModelRun(model_profile_id=uuid.UUID(m["model_profile_id"]), runs=m["runs"], params=m["params"])
            for m in baseline.config["models"]
        ]
        return ExperimentCreate(
            name=f"Candidate: {name}"[:200],
            dataset_version_id=baseline.dataset_version_id,
            split_scope=scope,
            models=models,
            evaluator_set_version_id=await self._results.scored_with(baseline),
        )

    async def _spec(self, baseline: Experiment) -> dict[str, Any]:
        version = await self._datasets.approved_version(baseline.project_id, baseline.dataset_version_id)
        record = await self._specs.get(baseline.project_id, version.task_spec_id) if version.task_spec_id else None
        return record.spec if record else {}

    async def _finish(self, session_id: uuid.UUID, stage: SessionStage, message: str) -> None:
        await self._repo.update_session(session_id, {"stage": stage, "message": message})
        await self._session.commit()
