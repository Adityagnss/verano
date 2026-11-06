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

from app.core.config import Settings, get_settings
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
from app.modules.evaluation.comparisons import case_results, comparison_out, versus_best
from app.modules.evaluation.domain import JudgeCandidate, check_instructions_fit, judge_calls_per_answer, suggest_judge
from app.modules.evaluation.domain import Score as ScoreValue
from app.modules.evaluation.labels import LabelService
from app.modules.evaluation.metrics import CaseOutcome, WeightedScore, case_result, model_metrics
from app.modules.evaluation.models import EvaluationRun, Score
from app.modules.evaluation.repository import ScoreRepository
from app.modules.evaluation.schemas import (
    CaseAgreement,
    CaseOutput,
    CaseResultOut,
    ComparisonOut,
    EvaluationRunOut,
    EvaluationRunStatus,
    EvaluationTrigger,
    EvaluatorSetVersionOut,
    JudgeCallOut,
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
    VersionComparisonOut,
    VersionModelComparison,
)
from app.modules.evaluation.service import EvaluatorSetService, judge_call_out
from app.modules.evaluation.significance import MIN_CASES, compare, seed_for
from app.modules.evaluation.stability import Answer, ModelStability, case_agreements, model_stability, replication
from app.modules.projects.schemas import ProjectOut
from app.modules.registry.service import RegistryService

EXPERIMENT_NOT_FOUND = "This experiment doesn't exist in this project."
RUN_NOT_FOUND = "This scoring run doesn't belong to this experiment."
NOTHING_CHANGED = "Nothing was changed, so there is nothing to score again. Use Score again to repeat the scoring."
NOT_SCORED = "This experiment hasn't been scored yet."
STILL_RUNNING = "Wait until the experiment has finished before rescoring it."
SCORE_JOB = "evaluation.score_experiment"
SCORED_STATES = {"completed", "cancelled", "failed"}
NOT_REPLICABLE = "These experiments weren't set up the same way, so comparing their answers is not a replication check."
SAME_EXPERIMENT = "Pick a different experiment to compare with."
OTHER_CHECKS = (
    "These experiments were scored with different checks or a different judge, so their scores can't be "
    "compared. Score one of them again with the other's checks and judge first."
)


class ResultsService:
    def __init__(
        self,
        session: AsyncSession,
        datasets: DatasetService,
        jobs: JobQueue,
        evaluators: EvaluatorSetService,
        registry: RegistryService,
        compare_min_cases: int = MIN_CASES,
        settings: Settings | None = None,
    ) -> None:
        self._session = session
        self._compare_min = compare_min_cases
        self._labels = LabelService(session, settings or get_settings())
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
            container.settings.compare_min_cases,
            container.settings,
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
            metrics = model_metrics(outcomes)
            versus = versus_best(run.id, experiment.id, metrics, outcomes, self._compare_min)
            models = [
                ModelMetricsOut(
                    **vars(m), **vars(stable.get(m.model_profile_id, nothing)), vs_best=versus.get(m.model_profile_id)
                )
                for m in metrics
            ]
        return ResultsOut(
            experiment_id=experiment.id,
            evaluation_run=EvaluationRunOut.model_validate(run) if run else None,
            evaluation_runs=[EvaluationRunOut.model_validate(r) for r in runs],
            models=models,
        )

    async def cases(
        self,
        project_id: uuid.UUID,
        experiment_id: uuid.UUID,
        run_id: uuid.UUID | None,
        failed_only: bool,
        user_id: uuid.UUID | None = None,
        blind: bool = False,
    ) -> list[CaseResultOut]:
        experiment = await self._experiment(project_id, experiment_id)
        run = self._pick(await self._scores.runs(experiment.id), run_id)
        if run is None:
            raise NotFound(NOT_SCORED)
        grouped: dict[uuid.UUID, list[CaseOutput]] = defaultdict(list)
        labelled = await self._labels.summaries_for(experiment.id, user_id)
        for outcome, row, scores in await self._outcomes(experiment, run):
            grouped[row.dataset_item_id].append(
                CaseOutput(
                    test_case_run_id=row.id,
                    model_profile_id=row.model_profile_id,
                    model=row.model,
                    run_number=row.run_number,
                    output=row.raw_output,
                    error=row.error_message,
                    passed=False if blind else outcome.passed,
                    quality=0.0 if blind else outcome.quality,
                    judged=False if blind else outcome.judged,
                    latency_ms=row.latency_ms,
                    cost=row.cost,
                    scores=[]
                    if blind
                    else [
                        ScoreOut(
                            evaluator_name=s.evaluator_name,
                            value=s.value,
                            passed=s.passed,
                            reason=s.reason,
                            status=ScoreStatus(s.status),
                        )
                        for s in scores
                    ],
                    truncated=row.output_truncated,
                    retrieved_chunks=row.retrieved_chunks,
                    tool_calls=row.tool_calls,
                    labels=labelled.get(row.id),
                    hidden=blind,
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
            if not failed_only or blind or any(not output.passed for output in grouped[item.id])
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
            "truncated",
            "human_label",
            "human_good",
            "human_bad",
            "human_unsure",
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
                        "yes" if o.truncated else "",
                        o.labels.verdict if o.labels else "",
                        o.labels.good if o.labels else "",
                        o.labels.bad if o.labels else "",
                        o.labels.unsure if o.labels else "",
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
        version = await self._base_version(experiment, body)
        if body.judge is not None or body.evaluators is not None:
            current = await self._evaluators.get_version(project.id, version)
            choice = body.judge or current.judge
            if choice is not None:
                target = await self._registry.call_target(project.id, choice.credential_id, choice.model)
                wanted = body.evaluators or current.evaluators
                check_instructions_fit([e.config for e in wanted], target.profile.context_window)
        if body.judge is not None or body.evaluators is not None:
            changed = await self._evaluators.with_changes(
                project.id,
                version,
                principal,
                evaluators=body.evaluators,
                judge=body.judge,
                change_reason=body.change_reason,
            )
            if body.evaluators is not None and body.judge is None and changed.id == version:
                raise Conflict(NOTHING_CHANGED)
            version = changed.id
        queued = EvaluationRun(
            experiment_id=experiment.id,
            evaluator_set_version_id=version,
            status=EvaluationRunStatus.PENDING,
            trigger=EvaluationTrigger.RESCORE,
        )
        await self._scores.add_run(queued)
        await self._session.commit()
        self._jobs.enqueue(
            SCORE_JOB,
            experiment_id=str(experiment.id),
            trigger="rescore",
            evaluator_set_version_id=str(version),
            evaluation_run_id=str(queued.id),
        )
        return await self.results(project.id, experiment_id, None)

    async def rescore_estimate(
        self, project: ProjectOut, experiment_id: uuid.UUID, body: RescoreRequest
    ) -> RescoreEstimate:
        """What scoring again would cost, from the answers already stored. Writes nothing."""
        experiment = await self._experiment(project.id, experiment_id)
        version = await self._evaluators.get_version(project.id, await self._base_version(experiment, body))
        choice = body.judge or version.judge
        if choice is None and experiment.config.get("judge"):
            stored = experiment.config["judge"]
            choice = JudgeChoice(credential_id=uuid.UUID(stored["credential_id"]), model=stored["model"])
        profile = None
        if choice is not None:
            profile = (await self._registry.call_target(project.id, choice.credential_id, choice.model)).profile
        checks = body.evaluators if body.evaluators is not None else version.evaluators
        judged_checks = judge_calls_per_answer([e.config for e in checks])
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

    async def _base_version(self, experiment: Experiment, body: RescoreRequest) -> uuid.UUID:
        """The checks being changed: the one named, else the ones the results show now, else the original."""
        shown = await self.scored_with(experiment)
        return body.evaluator_set_version_id or shown or experiment.evaluator_set_version_id

    async def judge_calls(
        self, project_id: uuid.UUID, experiment_id: uuid.UUID, test_case_run_id: uuid.UUID
    ) -> list[JudgeCallOut]:
        """Every judge call made about one answer, exactly as sent, oldest first."""
        await self._experiment(project_id, experiment_id)
        return [judge_call_out(call) for call in await self._scores.judge_calls(experiment_id, test_case_run_id)]

    async def scored_with(self, experiment: Experiment) -> uuid.UUID | None:
        """The evaluator-set version of the scoring pass the results show (the latest completed one)."""
        run = self._pick(await self._scores.runs(experiment.id), None)
        return run.evaluator_set_version_id if run else None

    async def same_scoring(self, first: Experiment, second: Experiment) -> bool:
        """Were the two scored the same way: the same checks with the same settings and the same judge? Compared
        by content, because every run that picks a judge saves its own evaluator-set version."""
        ids = (await self.scored_with(first), await self.scored_with(second))
        if ids[0] is None or ids[1] is None:
            return False
        if ids[0] == ids[1]:
            return True
        a = await self._evaluators.get_version(first.project_id, ids[0])
        b = await self._evaluators.get_version(second.project_id, ids[1])
        return _scoring_content(a) == _scoring_content(b)

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
                p.context_window,
            )
            for p in profiles
        ]
        best, reason = suggest_judge(candidates)
        return JudgeSuggestion(
            suggested=JudgeChoice(credential_id=best.credential_id, model=best.model) if best else None,
            reason=reason,
            candidates=[JudgeChoice(credential_id=c.credential_id, model=c.model) for c in candidates],
        )

    async def compare_versions(
        self, project_id: uuid.UUID, experiment_id: uuid.UUID, against_id: uuid.UUID
    ) -> VersionComparisonOut:
        """`experiment_id` (usually the newer prompt version) against `against_id`, per model, on the cases both
        judged. Refused when the two were scored differently, since their numbers would not mean the same."""
        if experiment_id == against_id:
            raise Conflict(SAME_EXPERIMENT)
        current = await self._experiment(project_id, experiment_id)
        earlier = await self._experiment(project_id, against_id)
        if any(e.status.value not in SCORED_STATES for e in (current, earlier)):
            raise Conflict(STILL_RUNNING)
        if not await self.same_scoring(current, earlier):
            raise Conflict(OTHER_CHECKS)
        now, before = await self.outcomes(current), await self.outcomes(earlier)
        names = {m["model_profile_id"]: m["display_name"] for m in current.config["models"]}
        numbers = await self._engine.prompt_numbers([current.prompt_version_id, earlier.prompt_version_id])
        models = []
        for model_id in sorted({o.model_profile_id for o in now} & {o.model_profile_id for o in before}, key=str):
            mine = case_results(o for o in now if o.model_profile_id == model_id)
            theirs = case_results(o for o in before if o.model_profile_id == model_id)
            common = set(mine) & set(theirs)
            models.append(
                VersionModelComparison(
                    model_profile_id=model_id,
                    model=names.get(str(model_id), str(model_id)),
                    comparison=comparison_out(
                        compare(
                            mine, theirs, seed=seed_for(current.id, earlier.id, model_id), min_cases=self._compare_min
                        )
                    ),
                    fixed=sorted(uuid.UUID(c) for c in common if mine[c].passed and not theirs[c].passed),
                    broken=sorted(uuid.UUID(c) for c in common if theirs[c].passed and not mine[c].passed),
                )
            )
        return VersionComparisonOut(
            experiment_id=current.id,
            against_id=earlier.id,
            prompt_version=numbers.get(current.prompt_version_id),
            against_prompt_version=numbers.get(earlier.prompt_version_id),
            same_test_cases=current.dataset_version_id == earlier.dataset_version_id,
            models=models,
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
        quality = await self._quality_between(current, earlier)
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
                quality=quality.get(model_id),
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

    async def _quality_between(self, current: Experiment, earlier: Experiment) -> dict[uuid.UUID, ComparisonOut]:
        """Did the scores move between a run and its re-run? The same engine as everywhere else, per model, on
        the cases judged in both; nothing when the two were scored with different checks or a different judge."""
        if not await self.same_scoring(current, earlier):
            return {}
        now, before = await self.outcomes(current), await self.outcomes(earlier)
        found = {}
        for model_id in {o.model_profile_id for o in now}:
            result = compare(
                case_results(o for o in now if o.model_profile_id == model_id),
                case_results(o for o in before if o.model_profile_id == model_id),
                seed=seed_for(current.id, earlier.id, model_id),
                min_cases=self._compare_min,
            )
            found[model_id] = comparison_out(result)
        return found

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


def _scoring_content(version: EvaluatorSetVersionOut) -> tuple[object, ...]:
    checks = tuple(
        (c.evaluator_name, c.evaluator_version, repr(sorted(c.config.items())), c.threshold, c.weight, c.required)
        for c in sorted(version.evaluators, key=lambda c: c.position)
    )
    judge = (str(version.judge.credential_id), version.judge.model) if version.judge else None
    return checks, judge
