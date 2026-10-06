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

import uuid
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
from app.modules.registry.service import RegistryService

PROMPTS_DIR = Path(__file__).parent / "prompts"
MAX_EXAMPLES = 8
TERMINAL = {"completed", "cancelled", "failed"}
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

    async def improve(self, session_id: uuid.UUID) -> None:
        row = await self._repo.session(session_id)
        if row is None or row.stage != SessionStage.ANALYZING or row.baseline_experiment_id is None:
            return
        baseline = await self._engine.experiment(row.baseline_experiment_id)
        assert baseline is not None
        try:
            await self._improve(row, baseline)
        except AppError as exc:
            await self._session.rollback()
            await self._finish(row.id, SessionStage.FAILED, exc.message)

    async def advance(self, experiment_id: uuid.UUID) -> None:
        candidate = await self._repo.candidate_for_experiment(experiment_id)
        if candidate is None:
            return
        row = await self._repo.session(candidate.session_id)
        assert row is not None
        if candidate.holdout_experiment_id == experiment_id:
            await self._conclude(row, candidate)
        elif row.stage == SessionStage.TESTING:
            await self._confirm_best(row)

    async def _improve(self, row: OptimizationSession, baseline: Experiment) -> None:
        run = next((r for r in await self._scores.runs(baseline.id) if r.status.value == "completed"), None)
        assert run is not None
        cases = await self._results.cases(baseline.project_id, baseline.id, run.id, failed_only=True)
        failures = failures_of([c for c in cases if c.split == Split.OPTIMIZE.value])
        if not failures:
            await self._finish(row.id, SessionStage.DONE, NO_FAILURES)
            return
        prompt = await self._prompts.get_version(baseline.project_id, baseline.prompt_version_id)
        spec = await self._spec(baseline)
        groups = await self._ask(
            baseline, row.writer, "failures.jinja", FailureGroups, "failure_groups", prompt, spec, cases=failures
        )
        clusters = await store_clusters(self._repo, baseline, run.id, groups, failures)
        drafts = await self._ask(
            baseline,
            row.writer,
            "candidates.jinja",
            CandidateDrafts,
            "candidates",
            prompt,
            spec,
            shape=prompt.shape.value,
            groups=[{"name": c.name, "size": c.size, "hypothesis": c.hypothesis} for c in clusters],
            examples=failures[:MAX_EXAMPLES],
        )
        created = await store_candidates(self._repo, self._prompts, row, baseline, prompt, drafts, clusters)
        if not created:
            await self._finish(row.id, SessionStage.FAILED, NO_CANDIDATES)
            return
        await self._repo.update_session(row.id, {"stage": SessionStage.TESTING})
        await self._session.commit()
        for candidate in created:
            experiment = await self._experiments.start(
                baseline.project_id,
                None,
                await self._rerun(baseline, SplitScope.OPTIMIZE, candidate.strategy),
                ExperimentOrigin.OPTIMIZATION,
                candidate.prompt_version_id,
            )
            await self._repo.update_candidate(candidate.id, {"optimize_experiment_id": experiment.id})
            await self._session.commit()

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
        chosen = writer or baseline.config.get("judge")
        if not chosen:
            raise AppError(NO_MODEL)
        target = await self._registry.call_target(
            baseline.project_id, uuid.UUID(chosen["credential_id"]), chosen["model"]
        )
        await self._session.commit()
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

    async def _confirm_best(self, row: OptimizationSession) -> None:
        candidates = await self._repo.candidates(row.id)
        experiments = {
            c.id: await self._engine.experiment(c.optimize_experiment_id)
            for c in candidates
            if c.optimize_experiment_id
        }
        if len(experiments) < len(candidates) or any(
            e is None or e.status.value not in TERMINAL for e in experiments.values()
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
        if await self._results.scored_with(holdout) != await self._results.scored_with(baseline):
            proof = VerdictOut(
                reason=Reason.DIFFERENT_JUDGE, message=DIFFERENT_JUDGE, minimum_cases=self._minimum, comparison=None
            )
        elif not (new_judged and old_judged):
            proof = VerdictOut(reason=Reason.UNJUDGED, message=UNJUDGED, minimum_cases=self._minimum, comparison=None)
        else:
            found = compare(new, old, seed=seed_for(holdout.id, baseline.id))
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
