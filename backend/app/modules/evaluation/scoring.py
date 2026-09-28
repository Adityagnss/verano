"""
Scoring (DEVELOPMENT.md 4.1): one EvaluationRun per pass over an experiment's calls.

Each succeeded call is checked by every evaluator in the evaluator-set version: our rule
evaluators first (free), then DeepEval G-Eval judges through the gateway, at most
`judge_concurrency` judge calls at a time. A failed call gets one `call_error` score of 0,
so it counts as a failed case. Outputs are never changed: rescoring (for example after a
rubric edit) creates a new EvaluationRun with its own scores (ADR 0004). A judge call that
fails is left out of that case's score rather than failing the model. When the initial
pass finishes, an experiment waiting to be scored is completed, and an improvement
session that ran it is moved on.
"""

import asyncio
import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.container import Container
from app.core.errors import AppError
from app.core.ids import uuid7
from app.core.jobs import JobQueue
from app.core.security import utcnow
from app.modules.datasets.models import DatasetItem
from app.modules.datasets.service import DatasetService
from app.modules.engine.models import Experiment, TestCaseRun
from app.modules.engine.repository import EngineRepository
from app.modules.engine.schemas import ExperimentOrigin, ExperimentStatus, RunStatus
from app.modules.engine.service import ExperimentService
from app.modules.evaluation.domain import EvalCase, Score
from app.modules.evaluation.models import EvaluationRun, EvaluatorConfig
from app.modules.evaluation.plugins.deepeval_adapter import judge
from app.modules.evaluation.plugins.rules import RULES
from app.modules.evaluation.repository import EvaluatorRepository, ScoreRepository
from app.modules.evaluation.schemas import EvaluationRunStatus, EvaluationTrigger
from app.modules.gateway.dependencies import build_gateway
from app.modules.gateway.schemas import CallContext
from app.modules.gateway.service import GatewayService
from app.modules.generator.repository import TaskSpecRepository
from app.modules.generator.schemas import TaskSpec
from app.modules.registry.schemas import CallTarget
from app.modules.registry.service import RegistryService

log = logging.getLogger(__name__)
ADVANCE_JOB = "assistant.advance"
CALL_ERROR = "call_error"
DEEPEVAL = "deepeval"


class ScoringService:
    def __init__(self, session: AsyncSession, container: Container) -> None:
        self._session = session
        self._settings = container.settings
        self._registry = RegistryService(session, container)
        self._gateway: GatewayService = build_gateway(container, self._registry)
        self._engine = EngineRepository(session)
        self._experiments = ExperimentService.from_container(session, container)
        self._datasets = DatasetService(session, container.settings)
        self._evaluators = EvaluatorRepository(session)
        self._scores = ScoreRepository(session)
        self._specs = TaskSpecRepository(session)
        self._jobs: JobQueue = container.jobs

    async def score(
        self,
        experiment_id: uuid.UUID,
        trigger: EvaluationTrigger = EvaluationTrigger.INITIAL,
        evaluator_set_version_id: uuid.UUID | None = None,
    ) -> uuid.UUID | None:
        experiment = await self._engine.experiment(experiment_id)
        if experiment is None:
            return None
        version_id = evaluator_set_version_id or experiment.evaluator_set_version_id
        run = EvaluationRun(
            experiment_id=experiment.id,
            evaluator_set_version_id=version_id,
            status=EvaluationRunStatus.RUNNING,
            trigger=trigger,
        )
        await self._scores.add_run(run)
        configs = await self._evaluators.configs(version_id)
        rows = await self._engine.runs(experiment.id)
        items = {
            i.id: i
            for i in await self._datasets.items(experiment.dataset_version_id, ids=[r.dataset_item_id for r in rows])
        }
        spec = await self._spec(experiment)
        target = await self._judge_target(experiment)
        await self._session.commit()
        limit = asyncio.Semaphore(self._settings.judge_concurrency)
        batches = await asyncio.gather(
            *(
                self._score_call(experiment, run.id, row, items[row.dataset_item_id], configs, spec, target, limit)
                for row in rows
            )
        )
        await self._scores.insert_scores([score for batch in batches for score in batch])
        await self._scores.finish_run(run.id, EvaluationRunStatus.COMPLETED, utcnow())
        await self._complete(experiment, trigger)
        await self._session.commit()
        return run.id

    async def _complete(self, experiment: Experiment, trigger: EvaluationTrigger) -> None:
        if trigger is not EvaluationTrigger.INITIAL:
            return
        if experiment.status is ExperimentStatus.EVALUATING:
            await self._experiments.transition(
                experiment, ExperimentStatus.COMPLETED, values={"completed_at": utcnow()}
            )
        if experiment.origin is ExperimentOrigin.OPTIMIZATION:
            await self._session.commit()
            self._jobs.enqueue(ADVANCE_JOB, experiment_id=str(experiment.id))

    async def _spec(self, experiment: Experiment) -> TaskSpec:
        version = await self._datasets.approved_version(experiment.project_id, experiment.dataset_version_id)
        record = await self._specs.get(experiment.project_id, version.task_spec_id) if version.task_spec_id else None
        if record is None:
            raise AppError("This dataset version has no Task Spec, so its cases can't be scored.")
        return TaskSpec.model_validate(record.spec)

    async def _judge_target(self, experiment: Experiment) -> CallTarget | None:
        judge_config = experiment.config.get("judge")
        if not judge_config:
            return None
        try:
            return await self._registry.call_target(
                experiment.project_id, uuid.UUID(judge_config["credential_id"]), judge_config["model"]
            )
        except AppError:
            log.warning("judge model unavailable for experiment %s", experiment.id)
            return None

    async def _score_call(
        self,
        experiment: Experiment,
        run_id: uuid.UUID,
        row: TestCaseRun,
        item: DatasetItem,
        configs: list[EvaluatorConfig],
        spec: TaskSpec,
        target: CallTarget | None,
        limit: asyncio.Semaphore,
    ) -> list[dict[str, Any]]:
        base = {"experiment_id": experiment.id, "evaluation_run_id": run_id, "test_case_run_id": row.id, "extra": {}}
        if row.status is RunStatus.FAILED:
            reason = row.error_message or "The call failed."
            return [
                base
                | {
                    "id": uuid7(),
                    "evaluator_name": CALL_ERROR,
                    "evaluator_version": "1",
                    "value": 0.0,
                    "passed": False,
                    "required": True,
                    "weight": 1.0,
                    "reason": reason,
                    "llm_call_id": None,
                }
            ]
        if row.status is not RunStatus.SUCCEEDED:
            return []
        case = EvalCase(
            inputs=item.inputs,
            output=row.raw_output or "",
            expected=item.expected_output,
            rubric=[str(c) for c in item.rubric] if item.rubric else None,
            task_spec=spec,
            context=[str(c) for c in item.context],
        )
        context = CallContext(project_id=experiment.project_id, experiment_id=experiment.id, test_case_run_id=row.id)
        scored = []
        for config in configs:
            result = await self._evaluate(config, case, target, context, limit)
            if result is not None:
                scored.append(
                    base
                    | {
                        "id": uuid7(),
                        "evaluator_name": config.evaluator_name,
                        "evaluator_version": config.evaluator_version,
                        "value": result.value,
                        "passed": result.passed,
                        "required": config.required,
                        "weight": config.weight,
                        "reason": result.reason[:4000],
                        "llm_call_id": None,
                    }
                )
        return scored

    async def _evaluate(
        self,
        config: EvaluatorConfig,
        case: EvalCase,
        target: CallTarget | None,
        context: CallContext,
        limit: asyncio.Semaphore,
    ) -> Score | None:
        if config.config.get("kind") != DEEPEVAL:
            rule = RULES.get(config.evaluator_name)
            return rule(case, config.config, config.threshold) if rule else None
        if target is None:
            return None
        async with limit:
            try:
                return await judge(
                    self._gateway, target, context, config.evaluator_name, config.config, config.threshold, case
                )
            except AppError as exc:
                log.warning("judge %s failed: %s", config.evaluator_name, exc.message)
                return None
