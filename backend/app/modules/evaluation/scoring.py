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
import json
import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.container import Container
from app.core.errors import AppError, Conflict, NotFound, ValidationFailed
from app.core.ids import uuid7
from app.core.jobs import JobQueue
from app.core.security import utcnow
from app.modules.datasets.models import DatasetItem
from app.modules.datasets.service import DatasetService
from app.modules.engine.estimate import estimate_judging
from app.modules.engine.models import Experiment, TestCaseRun
from app.modules.engine.repository import EngineRepository
from app.modules.engine.schemas import ExperimentOrigin, ExperimentStatus, RunStatus
from app.modules.engine.service import ExperimentService
from app.modules.evaluation.domain import EvalCase, Score, Unscored, check_instructions_fit, judge_calls_per_answer
from app.modules.evaluation.models import EvaluationRun, EvaluatorConfig
from app.modules.evaluation.plugins.deepeval_adapter import instructions_for, judge
from app.modules.evaluation.plugins.rules import RULES
from app.modules.evaluation.repository import EvaluatorRepository, ScoreRepository
from app.modules.evaluation.schemas import (
    EvaluationRunStatus,
    EvaluationTrigger,
    JudgeChoice,
    ScoreOut,
    ScoreStatus,
    TryJudgeEstimate,
    TryJudgeOut,
    TryJudgeRequest,
)
from app.modules.evaluation.service import judge_call_out
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
NO_JUDGE = "No judge model is available, so this answer could not be judged."
NOT_TRYABLE = "Only a judged check can be tried on an answer."
NOT_APPLICABLE = "This check does not apply to this answer: it uses the test case's own rubric and the case has none."
NO_SUCH_ANSWER = "This answer doesn't belong to this experiment, or it has no output to judge."
JUDGE_FAILED = "The judge could not score this answer: {why}"


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
        evaluation_run_id: uuid.UUID | None = None,
    ) -> uuid.UUID | None:
        """One scoring pass. A pass that was queued with its run already created (a rescore) is claimed first, so
        a job delivered twice scores once; a pass that fails is marked failed instead of staying "running"."""
        experiment = await self._engine.experiment(experiment_id)
        if experiment is None:
            return None
        if evaluation_run_id is not None:
            run = await self._scores.claim_run(evaluation_run_id)
            if run is None:
                return None
            await self._session.commit()
            version_id = run.evaluator_set_version_id
        else:
            version_id = evaluator_set_version_id or experiment.evaluator_set_version_id
            run = EvaluationRun(
                experiment_id=experiment.id,
                evaluator_set_version_id=version_id,
                status=EvaluationRunStatus.RUNNING,
                trigger=trigger,
            )
            await self._scores.add_run(run)
        try:
            await self._score_pass(experiment, run, version_id)
        except Exception:
            await self._session.rollback()
            await self._scores.finish_run(run.id, EvaluationRunStatus.FAILED, utcnow())
            await self._session.commit()
            raise
        await self._scores.finish_run(run.id, EvaluationRunStatus.COMPLETED, utcnow())
        await self._complete(experiment, trigger)
        await self._session.commit()
        return run.id

    async def _score_pass(self, experiment: Experiment, run: EvaluationRun, version_id: uuid.UUID) -> None:
        configs = await self._evaluators.configs(version_id)
        rows = await self._engine.runs(experiment.id)
        items = {
            i.id: i
            for i in await self._datasets.items(experiment.dataset_version_id, ids=[r.dataset_item_id for r in rows])
        }
        spec = await self._spec(experiment)
        target = await self._judge_target(experiment, version_id)
        await self._session.commit()
        limit = asyncio.Semaphore(self._settings.judge_concurrency)
        shared: dict[str, asyncio.Future[Score | Unscored | None]] = {}
        batches = await asyncio.gather(
            *(
                self._score_call(
                    experiment, run.id, row, items[row.dataset_item_id], configs, spec, target, limit, shared
                )
                for row in rows
            )
        )
        await self._scores.insert_scores([score for batch in batches for score in batch])

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

    async def _judge_target(self, experiment: Experiment, version_id: uuid.UUID) -> CallTarget | None:
        """The judge of the evaluator-set version being scored with; the experiment's own record for older versions."""
        judge_config = await self._evaluators.judge_of(version_id) or experiment.config.get("judge")
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
        shared: dict[str, "asyncio.Future[Score | Unscored | None]"],
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
        contexts = [
            CallContext(
                project_id=experiment.project_id,
                experiment_id=experiment.id,
                test_case_run_id=row.id,
                labels={"evaluation_run_id": str(run_id), "evaluator": config.evaluator_name},
            )
            for config in configs
        ]
        # the checks of one answer run side by side, so a slow judge does not hold up the others
        results = await asyncio.gather(
            *(
                self._evaluate_once(config, case, target, context, limit, shared)
                for config, context in zip(configs, contexts, strict=True)
            )
        )
        scored = []
        for config, result in zip(configs, results, strict=True):
            if result is None:
                continue
            if isinstance(result, Unscored):
                value, passed, status = 0.0, False, ScoreStatus.UNSCORED
            else:
                value, passed, status = result.value, result.passed, ScoreStatus.SCORED
            scored.append(
                base
                | {
                    "id": uuid7(),
                    "evaluator_name": config.evaluator_name,
                    "evaluator_version": config.evaluator_version,
                    "value": value,
                    "passed": passed,
                    "status": status,
                    "required": config.required,
                    "weight": config.weight,
                    "reason": result.reason[:4000],
                    "llm_call_id": None,
                }
            )
        return scored

    async def _evaluate_once(
        self,
        config: EvaluatorConfig,
        case: EvalCase,
        target: CallTarget | None,
        context: CallContext,
        limit: asyncio.Semaphore,
        shared: dict[str, "asyncio.Future[Score | Unscored | None]"],
    ) -> Score | Unscored | None:
        """Identical answers to identical inputs get one judge call per check in a scoring pass: the judge sees
        exactly the same thing, so a second call would only repeat the cost. A failed call is never shared."""
        if config.config.get("kind") != DEEPEVAL or target is None:
            return await self._evaluate(config, case, target, context, limit)
        key = json.dumps(
            [
                config.evaluator_name,
                config.config,
                config.threshold,
                case.inputs,
                case.output,
                case.expected,
                case.rubric,
                case.context,
            ],
            sort_keys=True,
            default=str,
        )
        task = shared.get(key)
        if task is None:
            task = shared[key] = asyncio.ensure_future(self._evaluate(config, case, target, context, limit))
            return await task
        result = await task
        if isinstance(result, Unscored):
            return await self._evaluate(config, case, target, context, limit)
        return result

    async def _evaluate(
        self,
        config: EvaluatorConfig,
        case: EvalCase,
        target: CallTarget | None,
        context: CallContext,
        limit: asyncio.Semaphore,
    ) -> Score | Unscored | None:
        """A score; None when the evaluator does not apply to this case; Unscored when it applies but failed."""
        if config.config.get("kind") != DEEPEVAL:
            rule = RULES.get(config.evaluator_name)
            return rule(case, config.config, config.threshold) if rule else None
        if instructions_for(config.config, case) is None:
            return None
        if target is None:
            return Unscored(NO_JUDGE)
        async with limit:
            try:
                return await judge(
                    self._gateway, target, context, config.evaluator_name, config.config, config.threshold, case
                )
            except AppError as exc:
                log.warning("judge %s failed: %s", config.evaluator_name, exc.message)
                return Unscored(JUDGE_FAILED.format(why=exc.message))
            except Exception as exc:
                log.warning("judge %s failed unexpectedly", config.evaluator_name, exc_info=True)
                return Unscored(JUDGE_FAILED.format(why=f"{type(exc).__name__}: {str(exc)[:200]}"))

    async def try_estimate(
        self, project_id: uuid.UUID, experiment_id: uuid.UUID, body: TryJudgeRequest
    ) -> TryJudgeEstimate:
        """What trying one judged check on one stored answer would cost. Writes nothing."""
        _, row, _, choice = await self._try_inputs(project_id, experiment_id, body)
        profile = None
        if choice is not None:
            profile = (await self._registry.call_target(project_id, choice.credential_id, choice.model)).profile
        calls, cost = estimate_judging(
            profile, [(row.input_tokens or 0, row.output_tokens or 0)], judge_calls_per_answer([body.evaluator.config])
        )
        return TryJudgeEstimate(
            judge_calls=calls,
            judge_cost=cost,
            price_known=cost is not None,
            judge_model=choice.model if choice else None,
        )

    async def try_judge(self, project_id: uuid.UUID, experiment_id: uuid.UUID, body: TryJudgeRequest) -> TryJudgeOut:
        """Runs one judged check on one stored answer: the judge's calls are recorded (and costed to the
        experiment) and labelled as a preview, but nothing is scored and no results change."""
        experiment, row, item, choice = await self._try_inputs(project_id, experiment_id, body)
        if choice is None:
            raise ValidationFailed(NO_JUDGE)
        target = await self._registry.call_target(project_id, choice.credential_id, choice.model)
        check_instructions_fit([body.evaluator.config], target.profile.context_window)
        spec = await self._spec(experiment)
        case = EvalCase(
            inputs=item.inputs,
            output=row.raw_output or "",
            expected=item.expected_output,
            rubric=[str(c) for c in item.rubric] if item.rubric else None,
            task_spec=spec,
            context=[str(c) for c in item.context],
        )
        name = body.evaluator.evaluator_name
        context = CallContext(
            project_id=project_id,
            experiment_id=experiment.id,
            test_case_run_id=row.id,
            labels={"preview": "true", "evaluator": name},
        )
        config = EvaluatorConfig(
            evaluator_name=name,
            evaluator_version=body.evaluator.evaluator_version,
            config=body.evaluator.config,
            threshold=body.evaluator.threshold,
            weight=body.evaluator.weight,
            required=body.evaluator.required,
        )
        started = utcnow()
        result = await self._evaluate(config, case, target, context, asyncio.Semaphore(1))
        if result is None:
            raise Conflict(NOT_APPLICABLE)
        await self._session.commit()
        calls = [
            c
            for c in await self._scores.judge_calls(experiment.id, row.id)
            if c.labels.get("preview") == "true" and c.created_at >= started
        ]
        if isinstance(result, Unscored):
            shown = ScoreOut(
                evaluator_name=name, value=0.0, passed=False, reason=result.reason, status=ScoreStatus.UNSCORED
            )
        else:
            shown = ScoreOut(evaluator_name=name, value=result.value, passed=result.passed, reason=result.reason)
        return TryJudgeOut(score=shown, calls=[judge_call_out(c) for c in calls])

    async def _try_inputs(
        self, project_id: uuid.UUID, experiment_id: uuid.UUID, body: TryJudgeRequest
    ) -> tuple[Experiment, TestCaseRun, DatasetItem, JudgeChoice | None]:
        if body.evaluator.config.get("kind") != DEEPEVAL:
            raise ValidationFailed(NOT_TRYABLE)
        experiment = await self._engine.experiment(experiment_id, project_id)
        if experiment is None:
            raise NotFound("This experiment doesn't exist in this project.")
        row = next((r for r in await self._engine.runs(experiment.id) if r.id == body.test_case_run_id), None)
        if row is None or row.status is not RunStatus.SUCCEEDED:
            raise NotFound(NO_SUCH_ANSWER)
        item = (await self._datasets.items(experiment.dataset_version_id, ids=[row.dataset_item_id]))[0]
        runs = await self._scores.runs(experiment.id)
        shown = next((r.evaluator_set_version_id for r in runs if r.status is EvaluationRunStatus.COMPLETED), None)
        choice = body.judge
        if choice is None:
            stored = await self._evaluators.judge_of(
                shown or experiment.evaluator_set_version_id
            ) or experiment.config.get("judge")
            if stored:
                choice = JudgeChoice(credential_id=uuid.UUID(str(stored["credential_id"])), model=stored["model"])
        return experiment, row, item, choice
