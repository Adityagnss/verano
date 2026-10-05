"""
Results (DEVELOPMENT.md 4.2-4.4, base level): the per-model tradeoff table, the case view
with every model's output side by side, CSV export, and rescoring.

Results always come from one EvaluationRun (the latest finished one unless another is
asked for), so numbers are only ever combined across calls scored with the same evaluator
set version. Rescoring queues a new EvaluationRun; earlier runs stay readable.
"""

import csv
import io
import json
import uuid
from collections import defaultdict

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.container import Container
from app.core.errors import Conflict, NotFound
from app.core.jobs import JobQueue
from app.core.security import Principal
from app.modules.datasets.service import DatasetService
from app.modules.engine.estimate import estimate_judging
from app.modules.engine.fingerprint import config_hash
from app.modules.engine.models import Experiment, TestCaseRun
from app.modules.engine.provenance import changed_between, known, summarize
from app.modules.engine.repository import EngineRepository
from app.modules.engine.schemas import RunStatus
from app.modules.evaluation.domain import JudgeCandidate, suggest_judge
from app.modules.evaluation.domain import Score as ScoreValue
from app.modules.evaluation.metrics import CaseOutcome, WeightedScore, case_result, model_metrics
from app.modules.evaluation.models import EvaluationRun, Score
from app.modules.evaluation.repository import ScoreRepository
from app.modules.evaluation.schemas import (
    CaseAgreement,
    CaseOutput,
    CaseResultOut,
    EvaluationRunOut,
    EvaluationRunStatus,
    EvaluatorSetVersionOut,
    JudgeChoice,
    JudgeSuggestion,
    ModelMetricsOut,
    ReplicationModel,
    ReplicationOut,
    RescoreEstimate,
    RescoreRequest,
    ResultsOut,
    ScoreOut,
    ScoreStatus,
)
from app.modules.evaluation.service import EvaluatorSetService
from app.modules.evaluation.stability import Answer, ModelStability, case_agreements, model_stability, replication
from app.modules.projects.schemas import ProjectOut
from app.modules.registry.service import RegistryService

EXPERIMENT_NOT_FOUND = "This experiment doesn't exist in this project."
RUN_NOT_FOUND = "This scoring run doesn't belong to this experiment."
NOT_SCORED = "This experiment hasn't been scored yet."
STILL_RUNNING = "Wait until the experiment has finished before rescoring it."
SCORE_JOB = "evaluation.score_experiment"
SCORED_STATES = {"completed", "cancelled", "failed"}
NOT_REPLICABLE = "These experiments weren't set up the same way, so comparing their answers is not a replication check."
SAME_EXPERIMENT = "Pick a different experiment to compare with."


class ResultsService:
    def __init__(
        self,
        session: AsyncSession,
        datasets: DatasetService,
        jobs: JobQueue,
        evaluators: EvaluatorSetService,
        registry: RegistryService,
    ) -> None:
        self._session = session
        self._engine = EngineRepository(session)
        self._scores = ScoreRepository(session)
        self._datasets = datasets
        self._jobs = jobs
        self._evaluators = evaluators
        self._registry = registry

    @classmethod
    def from_container(cls, session: AsyncSession, container: Container) -> "ResultsService":
        return cls(
            session,
            DatasetService(session, container.settings),
            container.jobs,
            EvaluatorSetService(session),
            RegistryService(session, container),
        )

    async def results(self, project_id: uuid.UUID, experiment_id: uuid.UUID, run_id: uuid.UUID | None) -> ResultsOut:
        experiment = await self._experiment(project_id, experiment_id)
        runs = await self._scores.runs(experiment.id)
        run = self._pick(runs, run_id)
        models = []
        if run is not None:
            outcomes = [o for o, _, _ in await self._outcomes(experiment, run)]
            stable = model_stability(await self._answers(experiment))
            nothing = ModelStability(stability=None, stable_cases=0, compared_cases=0)
            models = [
                ModelMetricsOut(**vars(m), **vars(stable.get(m.model_profile_id, nothing)))
                for m in model_metrics(outcomes)
            ]
        return ResultsOut(
            experiment_id=experiment.id,
            evaluation_run=EvaluationRunOut.model_validate(run) if run else None,
            evaluation_runs=[EvaluationRunOut.model_validate(r) for r in runs],
            models=models,
        )

    async def cases(
        self, project_id: uuid.UUID, experiment_id: uuid.UUID, run_id: uuid.UUID | None, failed_only: bool
    ) -> list[CaseResultOut]:
        experiment = await self._experiment(project_id, experiment_id)
        run = self._pick(await self._scores.runs(experiment.id), run_id)
        if run is None:
            raise NotFound(NOT_SCORED)
        grouped: dict[uuid.UUID, list[CaseOutput]] = defaultdict(list)
        for outcome, row, scores in await self._outcomes(experiment, run):
            grouped[row.dataset_item_id].append(
                CaseOutput(
                    test_case_run_id=row.id,
                    model_profile_id=row.model_profile_id,
                    model=row.model,
                    run_number=row.run_number,
                    output=row.raw_output,
                    error=row.error_message,
                    passed=outcome.passed,
                    quality=outcome.quality,
                    judged=outcome.judged,
                    latency_ms=row.latency_ms,
                    cost=row.cost,
                    scores=[
                        ScoreOut(
                            evaluator_name=s.evaluator_name,
                            value=s.value,
                            passed=s.passed,
                            reason=s.reason,
                            status=ScoreStatus(s.status),
                        )
                        for s in scores
                    ],
                )
            )
        agreements = case_agreements(await self._answers(experiment))
        items = await self._datasets.items(experiment.dataset_version_id, ids=list(grouped))
        return [
            CaseResultOut(
                dataset_item_id=item.id,
                inputs=item.inputs,
                expected_output=item.expected_output,
                rubric=item.rubric,
                category=item.category,
                source=item.source.value,
                split=item.split.value if item.split else None,
                outputs=sorted(grouped[item.id], key=lambda o: (o.model, o.run_number)),
                agreement=[
                    CaseAgreement(model_profile_id=model_id, same=found.same, runs=found.runs)
                    for (model_id, item_id), found in agreements.items()
                    if item_id == item.id
                ],
            )
            for item in items
            if not failed_only or any(not output.passed for output in grouped[item.id])
        ]

    async def export_csv(self, project_id: uuid.UUID, experiment_id: uuid.UUID, run_id: uuid.UUID | None) -> str:
        cases = await self.cases(project_id, experiment_id, run_id, failed_only=False)
        names = sorted({s.evaluator_name for case in cases for o in case.outputs for s in o.scores})
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        header = [
            "case_id",
            "category",
            "source",
            "split",
            "inputs",
            "expected_output",
            "model",
            "run",
            "output",
            "error",
            "passed",
            "quality",
            "judged",
            "latency_ms",
            "cost",
        ]
        writer.writerow(header + names)
        for case in cases:
            for o in case.outputs:
                by_name = {s.evaluator_name: s.value for s in o.scores}
                writer.writerow(
                    [
                        case.dataset_item_id,
                        case.category,
                        case.source,
                        case.split,
                        json.dumps(case.inputs, ensure_ascii=False),
                        case.expected_output,
                        o.model,
                        o.run_number,
                        o.output,
                        o.error,
                        o.passed if o.judged else "",
                        round(o.quality, 4) if o.judged else "",
                        "yes" if o.judged else "no",
                        o.latency_ms,
                        o.cost,
                        *[by_name.get(name, "") for name in names],
                    ]
                )
        return buffer.getvalue()

    async def rescore(
        self, project: ProjectOut, principal: Principal, experiment_id: uuid.UUID, body: RescoreRequest
    ) -> ResultsOut:
        """Scores the stored answers again. With a different judge this is a new evaluator-set version (the
        same checks, another judge), so it is a separate scoring pass that is never mixed into the old one."""
        experiment = await self._experiment(project.id, experiment_id)
        if experiment.status.value not in SCORED_STATES:
            raise Conflict(STILL_RUNNING)
        version = body.evaluator_set_version_id or experiment.evaluator_set_version_id
        if body.judge is not None:
            await self._registry.call_target(project.id, body.judge.credential_id, body.judge.model)
            version = (await self._evaluators.with_judge(project.id, version, body.judge, principal)).id
        await self._session.commit()
        self._jobs.enqueue(
            SCORE_JOB, experiment_id=str(experiment.id), trigger="rescore", evaluator_set_version_id=str(version)
        )
        return await self.results(project.id, experiment_id, None)

    async def rescore_estimate(
        self, project: ProjectOut, experiment_id: uuid.UUID, body: RescoreRequest
    ) -> RescoreEstimate:
        """What scoring again would cost, from the answers already stored. Writes nothing."""
        experiment = await self._experiment(project.id, experiment_id)
        version = await self._evaluators.get_version(
            project.id, body.evaluator_set_version_id or experiment.evaluator_set_version_id
        )
        choice = body.judge or version.judge
        if choice is None and experiment.config.get("judge"):
            stored = experiment.config["judge"]
            choice = JudgeChoice(credential_id=uuid.UUID(stored["credential_id"]), model=stored["model"])
        profile = None
        if choice is not None:
            profile = (await self._registry.call_target(project.id, choice.credential_id, choice.model)).profile
        judged_checks = sum(1 for e in version.evaluators if e.config.get("kind") == "deepeval")
        answers = [
            (row.input_tokens or 0, row.output_tokens or 0)
            for row in await self._engine.runs(experiment.id)
            if row.status is RunStatus.SUCCEEDED
        ]
        calls, cost = estimate_judging(profile, answers, judged_checks)
        return RescoreEstimate(
            judge_calls=calls,
            judge_cost=cost,
            price_known=cost is not None,
            judge_model=choice.model if choice else None,
        )

    async def scored_with(self, experiment: Experiment) -> uuid.UUID | None:
        """The evaluator-set version of the scoring pass the results show (the latest completed one)."""
        run = self._pick(await self._scores.runs(experiment.id), None)
        return run.evaluator_set_version_id if run else None

    async def evaluator_version(self, project_id: uuid.UUID, version_id: uuid.UUID) -> EvaluatorSetVersionOut:
        return await self._evaluators.get_version(project_id, version_id)

    async def judge_suggestion(self, project: ProjectOut) -> JudgeSuggestion:
        profiles = await self._registry.all_profiles(project.id)
        candidates = [
            JudgeCandidate(
                p.credential_id,
                p.model_name,
                p.is_selected,
                float(p.output_price_per_mtok) if p.output_price_per_mtok is not None else None,
            )
            for p in profiles
        ]
        best, reason = suggest_judge(candidates)
        return JudgeSuggestion(
            suggested=JudgeChoice(credential_id=best.credential_id, model=best.model) if best else None,
            reason=reason,
            candidates=[JudgeChoice(credential_id=c.credential_id, model=c.model) for c in candidates],
        )

    async def replication(
        self, project_id: uuid.UUID, experiment_id: uuid.UUID, against_id: uuid.UUID
    ) -> ReplicationOut:
        """Call by call: did this experiment answer like an earlier one set up the same way?"""
        if experiment_id == against_id:
            raise Conflict(SAME_EXPERIMENT)
        current = await self._experiment(project_id, experiment_id)
        earlier = await self._experiment(project_id, against_id)
        if any(e.status.value not in SCORED_STATES for e in (current, earlier)):
            raise Conflict(STILL_RUNNING)
        if config_hash(current) != config_hash(earlier):
            raise Conflict(NOT_REPLICABLE)
        found = replication(await self._answers(current), await self._answers(earlier))
        names = {m["model_profile_id"]: m["display_name"] for m in current.config["models"]}
        now = summarize(await self._engine.returned_models(current.id))
        before = summarize(await self._engine.returned_models(earlier.id))
        models = [
            ReplicationModel(
                model_profile_id=model_id,
                model=names.get(str(model_id), ""),
                same=r.same,
                compared=r.compared,
                skipped=r.skipped,
                earlier_versions=sorted(known(before.get(model_id, []))),
                versions=sorted(known(now.get(model_id, []))),
                model_changed=changed_between(before.get(model_id, []), now.get(model_id, [])),
            )
            for model_id, r in found.items()
        ]
        return ReplicationOut(
            experiment_id=current.id,
            against_id=earlier.id,
            against_name=earlier.name,
            same=sum(m.same for m in models),
            compared=sum(m.compared for m in models),
            skipped=sum(m.skipped for m in models),
            model_changed=any(m.model_changed for m in models),
            models=models,
        )

    async def _answers(self, experiment: Experiment) -> list[Answer]:
        return [
            Answer(row.model_profile_id, row.dataset_item_id, row.run_number, row.raw_output or "")
            for row in await self._engine.runs(experiment.id)
            if row.status is RunStatus.SUCCEEDED
        ]

    async def outcomes(self, experiment: Experiment) -> list[CaseOutcome]:
        run = self._pick(await self._scores.runs(experiment.id), None)
        return [o for o, _, _ in await self._outcomes(experiment, run)] if run else []

    async def _outcomes(
        self, experiment: Experiment, run: EvaluationRun
    ) -> list[tuple[CaseOutcome, TestCaseRun, list[Score]]]:
        by_call: dict[uuid.UUID, list[Score]] = defaultdict(list)
        for score in await self._scores.scores(experiment.id, run.id):
            by_call[score.test_case_run_id].append(score)
        results = []
        for row in await self._engine.runs(experiment.id):
            if row.status not in (RunStatus.SUCCEEDED, RunStatus.FAILED):
                continue
            scores = by_call[row.id]
            weighted = [
                WeightedScore(
                    ScoreValue(value=s.value, passed=s.passed, reason=s.reason),
                    s.weight,
                    scored=s.status != ScoreStatus.UNSCORED,
                )
                for s in scores
            ]
            passed, quality, judged = case_result(weighted)
            failed = row.status is RunStatus.FAILED
            outcome = CaseOutcome(
                model_profile_id=row.model_profile_id,
                model=row.model,
                dataset_item_id=row.dataset_item_id,
                run_number=row.run_number,
                call_failed=failed,
                passed=passed and not failed,
                quality=0.0 if failed else quality,
                latency_ms=row.latency_ms,
                cost=row.cost,
                judged=judged,
            )
            results.append((outcome, row, scores))
        return results

    @staticmethod
    def _pick(runs: list[EvaluationRun], run_id: uuid.UUID | None) -> EvaluationRun | None:
        if run_id is not None:
            chosen = next((r for r in runs if r.id == run_id), None)
            if chosen is None:
                raise NotFound(RUN_NOT_FOUND)
            return chosen
        return next((r for r in runs if r.status is EvaluationRunStatus.COMPLETED), None)

    async def _experiment(self, project_id: uuid.UUID, experiment_id: uuid.UUID) -> Experiment:
        row = await self._engine.experiment(experiment_id, project_id)
        if row is None:
            raise NotFound(EXPERIMENT_NOT_FOUND)
        return row
