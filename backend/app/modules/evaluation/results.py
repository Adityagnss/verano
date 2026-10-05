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
from app.modules.datasets.service import DatasetService
from app.modules.engine.fingerprint import config_hash
from app.modules.engine.models import Experiment, TestCaseRun
from app.modules.engine.provenance import changed_between, known, summarize
from app.modules.engine.repository import EngineRepository
from app.modules.engine.schemas import RunStatus
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
    ModelMetricsOut,
    ReplicationModel,
    ReplicationOut,
    RescoreRequest,
    ResultsOut,
    ScoreOut,
)
from app.modules.evaluation.stability import Answer, ModelStability, case_agreements, model_stability, replication

EXPERIMENT_NOT_FOUND = "This experiment doesn't exist in this project."
RUN_NOT_FOUND = "This scoring run doesn't belong to this experiment."
NOT_SCORED = "This experiment hasn't been scored yet."
STILL_RUNNING = "Wait until the experiment has finished before rescoring it."
SCORE_JOB = "evaluation.score_experiment"
SCORED_STATES = {"completed", "cancelled", "failed"}
NOT_REPLICABLE = "These experiments weren't set up the same way, so comparing their answers is not a replication check."
SAME_EXPERIMENT = "Pick a different experiment to compare with."


class ResultsService:
    def __init__(self, session: AsyncSession, datasets: DatasetService, jobs: JobQueue) -> None:
        self._engine = EngineRepository(session)
        self._scores = ScoreRepository(session)
        self._datasets = datasets
        self._jobs = jobs

    @classmethod
    def from_container(cls, session: AsyncSession, container: Container) -> "ResultsService":
        return cls(session, DatasetService(session, container.settings), container.jobs)

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
                    latency_ms=row.latency_ms,
                    cost=row.cost,
                    scores=[
                        ScoreOut(evaluator_name=s.evaluator_name, value=s.value, passed=s.passed, reason=s.reason)
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
                        o.passed,
                        round(o.quality, 4),
                        o.latency_ms,
                        o.cost,
                        *[by_name.get(name, "") for name in names],
                    ]
                )
        return buffer.getvalue()

    async def rescore(self, project_id: uuid.UUID, experiment_id: uuid.UUID, body: RescoreRequest) -> ResultsOut:
        experiment = await self._experiment(project_id, experiment_id)
        if experiment.status.value not in SCORED_STATES:
            raise Conflict(STILL_RUNNING)
        version = body.evaluator_set_version_id or experiment.evaluator_set_version_id
        self._jobs.enqueue(
            SCORE_JOB, experiment_id=str(experiment.id), trigger="rescore", evaluator_set_version_id=str(version)
        )
        return await self.results(project_id, experiment_id, None)

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
                WeightedScore(ScoreValue(value=s.value, passed=s.passed, reason=s.reason), s.weight) for s in scores
            ]
            passed, quality = case_result(weighted)
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
