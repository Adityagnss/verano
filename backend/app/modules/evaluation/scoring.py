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
import hashlib
import logging
import uuid
from datetime import datetime
from typing import Any, cast

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.container import Container
from app.core.errors import AppError, Conflict, NotFound, ValidationFailed
from app.core.features import CODE_CHECKS, is_enabled
from app.core.ids import uuid7
from app.core.jobs import JobQueue
from app.core.leases import Heartbeat, deadline
from app.core.security import utcnow
from app.modules.datasets.models import DatasetItem
from app.modules.datasets.service import DatasetService
from app.modules.engine.estimate import estimate_judging
from app.modules.engine.models import Experiment, TestCaseRun
from app.modules.engine.repository import EngineRepository
from app.modules.engine.schemas import ExperimentOrigin, ExperimentStatus, RunStatus
from app.modules.engine.service import ExperimentService
from app.modules.evaluation.domain import EvalCase, Score, Unscored, check_instructions_fit, judge_calls_per_answer
from app.modules.evaluation.judge_cache import CachedResult, RecentResults, cache_key
from app.modules.evaluation.judging import (
    CombinedCheck,
    CombinedVerdicts,
    cache_extras,
    combined_prompt,
    prompt_text,
    read_combined,
    reference_of,
    sees_prompt,
    share_of,
)
from app.modules.evaluation.models import EvaluationRun, EvaluatorConfig
from app.modules.evaluation.plugins.deepeval_adapter import answer_text, instructions_for, judge
from app.modules.evaluation.plugins.rules import RULES
from app.modules.evaluation.repository import EvaluatorRepository, JudgeCacheRepository, ScoreRepository
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
from app.modules.gateway.schemas import CallContext, CallPurpose, LLMResult, Message
from app.modules.gateway.service import GatewayService
from app.modules.generator.repository import TaskSpecRepository
from app.modules.generator.schemas import TaskSpec
from app.modules.registry.schemas import CallTarget
from app.modules.registry.service import RegistryService
from app.sandbox.contract import SandboxLimits, SandboxRequest
from app.sandbox.factory import build_sandbox
from app.sandbox.runner import Sandbox

log = logging.getLogger(__name__)
ADVANCE_JOB = "assistant.advance"
CALL_ERROR = "call_error"
DEEPEVAL = "deepeval"
CODE = "code"
CHECK_BROKEN = "The check could not run: {why}"
NO_JUDGE = "No judge model is available, so this answer could not be judged."
NOT_TRYABLE = "Only a judged check can be tried on an answer."
NOT_APPLICABLE = "This check does not apply to this answer: it uses the test case's own rubric and the case has none."
NO_SUCH_ANSWER = "This answer doesn't belong to this experiment, or it has no output to judge."
JUDGE_FAILED = "The judge could not score this answer: {why}"
SKIPPED_FAST = "Skipped: a required free check already failed this answer, and fast scoring does not judge it then."
COMBINED = "combined"
FAST = "fast"


def _call_id(result: Score | Unscored) -> uuid.UUID | None:
    """The judge call a score came from, when it is known (a combined call's score records it)."""
    found = result.metadata.get("llm_call_id") if isinstance(result, Score) else None
    return uuid.UUID(str(found)) if found else None


def eval_case(
    item: DatasetItem, row: TestCaseRun, spec: TaskSpec, prompt_chars: int = 0, reference_on: bool = True
) -> EvalCase:
    """What the checks see of one answer: the case, the answer, and what an app reported with it (the chunks it
    retrieved are context for the judges, its tool calls are for the tool checks). The judges also read the
    prompt the model was sent (up to `prompt_chars` of it; 0 leaves it out) and may use the expected answer as
    their reference."""
    return EvalCase(
        inputs=item.inputs,
        output=row.raw_output or "",
        expected=item.expected_output,
        rubric=[str(c) for c in item.rubric] if item.rubric else None,
        task_spec=spec,
        context=[str(c) for c in item.context] + [str(c) for c in row.retrieved_chunks or []],
        tool_calls=[call for call in row.tool_calls or [] if isinstance(call, dict)],
        prompt=prompt_text(row.rendered_system_prompt, row.rendered_user_prompt, prompt_chars),
        reference_on=reference_on,
    )


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
        self._sessions = container.database.sessions
        self._sandbox: Sandbox = build_sandbox(container.settings.sandbox_url)
        self._recent = RecentResults(container.settings.judge_cache_recent_size)

    def _case(self, item: DatasetItem, row: TestCaseRun, spec: TaskSpec) -> EvalCase:
        settings = self._settings
        chars = settings.judge_prompt_max_chars if settings.judge_sees_prompt else 0
        return eval_case(item, row, spec, chars, settings.judge_uses_reference)

    def _fast(self, experiment: Experiment) -> bool:
        """Whether this pass scores in fast mode: the experiment's own `scoring_mode` when it has one, else the
        server's. Fast mode puts several judged checks of one answer into one judge call (ADR 0038)."""
        chosen = experiment.config.get("scoring_mode")
        mode = chosen if chosen in ("accurate", FAST) else self._settings.scoring_mode
        return mode == FAST and self._settings.combined_judge_enabled

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
            run = await self._scores.claim_run(evaluation_run_id, self._lease())
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
                lease_expires_at=self._lease(),
            )
            await self._scores.add_run(run)
        run_id = run.id

        async def beat() -> None:
            async with self._sessions() as own:
                await ScoreRepository(own).extend_run_lease(run_id, self._lease())
                await own.commit()

        try:
            async with Heartbeat(beat, self._settings.lease_seconds / 3):
                finished = await self._score_pass(experiment, run, version_id)
        except Exception:
            await self._session.rollback()
            await self._scores.finish_run(run.id, EvaluationRunStatus.FAILED, utcnow())
            await self._session.commit()
            raise
        if not finished:
            await self._scores.finish_run(run.id, EvaluationRunStatus.FAILED, utcnow())
            await self._session.commit()
            return run.id
        await self._scores.finish_run(run.id, EvaluationRunStatus.COMPLETED, utcnow())
        await self._complete(experiment, trigger)
        await self._session.commit()
        return run.id

    def _lease(self) -> datetime:
        return deadline(utcnow(), self._settings.lease_seconds)

    async def _score_pass(self, experiment: Experiment, run: EvaluationRun, version_id: uuid.UUID) -> bool:
        """Scores every answer; False when the experiment was stopped meanwhile (the pass is then left unfinished)."""
        configs = await self._evaluators.configs(version_id)
        done = await self._scores.scored_call_ids(run.id)  # a pass given to another worker carries on, not restarts
        rows = [r for r in await self._engine.runs(experiment.id) if r.id not in done]
        items = {
            i.id: i
            for i in await self._datasets.items(experiment.dataset_version_id, ids=[r.dataset_item_id for r in rows])
        }
        spec = await self._spec(experiment)
        target = await self._judge_target(experiment, version_id)
        await self._session.commit()
        limit = asyncio.Semaphore(self._settings.judge_concurrency)
        shared: dict[str, asyncio.Future[Score | Unscored | None]] = {}
        saving = asyncio.Lock()

        initial = run.trigger is EvaluationTrigger.INITIAL
        stopped = False

        async def score_and_save(row: TestCaseRun) -> None:
            nonlocal stopped
            if stopped:
                return
            batch = await self._score_call(
                experiment, run.id, row, items[row.dataset_item_id], configs, spec, target, limit, shared
            )
            # saved as each answer finishes (the pass is only read once it completes), so progress can be shown;
            # on a session of its own, so the objects the other answers are reading are not expired meanwhile
            async with saving, self._sessions() as own:
                await ScoreRepository(own).insert_scores(batch)
                await own.commit()
                current = await EngineRepository(own).experiment(experiment.id)
                stopped = initial and current is not None and current.status is ExperimentStatus.CANCELLED

        await asyncio.gather(*(score_and_save(row) for row in rows))
        return not stopped

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
        case = self._case(item, row, spec)
        contexts = [
            CallContext(
                project_id=experiment.project_id,
                experiment_id=experiment.id,
                test_case_run_id=row.id,
                labels={"evaluation_run_id": str(run_id), "evaluator": config.evaluator_name},
            )
            for config in configs
        ]
        results = await self._run_checks(experiment, run_id, configs, case, target, contexts, limit, shared)
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
                    "llm_call_id": _call_id(result),
                    "extra": self._evidence(config, case, result),
                }
            )
        return scored

    def _evidence(self, config: EvaluatorConfig, case: EvalCase, result: Score | Unscored) -> dict[str, Any]:
        """What a stored score remembers about how it was made: whether a judge produced it, whether it came
        from the cache, whether it ran as custom code, whether the judge was given the prompt and a reference
        answer, and whether it shared a combined call ("Why this score" and agreement read this)."""
        kind = config.config.get("kind")
        judged = kind == DEEPEVAL
        found: dict[str, Any] = {"judged": judged, "code": kind == CODE}
        if judged:
            found["prompt_seen"] = sees_prompt(config.config, case)
            found["reference_used"] = reference_of(config.config, case) is not None
        if isinstance(result, Score):
            if result.metadata.get("cached"):
                found["cached"] = True
            if result.metadata.get(COMBINED):
                found[COMBINED] = True
            if "usage" in result.metadata:
                found["usage"] = result.metadata["usage"]
        return found

    async def _run_checks(
        self,
        experiment: Experiment,
        run_id: uuid.UUID,
        configs: list[EvaluatorConfig],
        case: EvalCase,
        target: CallTarget | None,
        contexts: list[CallContext],
        limit: asyncio.Semaphore,
        shared: dict[str, "asyncio.Future[Any]"],
    ) -> list[Score | Unscored | None]:
        """Every check of one answer. Accurate mode (the default) runs them side by side, each judged check in
        its own judge call. Fast mode runs the free checks first and then scores the judged ones together in
        one judge call (several only when there are at least `combined_judge_min_checks` of them)."""
        if target is None or not self._fast(experiment):
            return list(
                await asyncio.gather(
                    *(
                        self._evaluate_once(config, case, target, context, limit, shared)
                        for config, context in zip(configs, contexts, strict=True)
                    )
                )
            )
        settings = self._settings
        results: list[Score | Unscored | None] = [None] * len(configs)
        free = [i for i, config in enumerate(configs) if config.config.get("kind") != DEEPEVAL]
        asked = [
            i
            for i, config in enumerate(configs)
            if config.config.get("kind") == DEEPEVAL and instructions_for(config.config, case) is not None
        ]
        done = await asyncio.gather(
            *(self._evaluate_once(configs[i], case, target, contexts[i], limit, shared) for i in free)
        )
        for i, result in zip(free, done, strict=True):
            results[i] = result
        if settings.fast_skip_judges_after_required_failure and any(
            configs[i].required and isinstance(r, Score) and not r.passed for i, r in zip(free, done, strict=True)
        ):
            for i in asked:
                results[i] = Unscored(SKIPPED_FAST)
            return results
        size = max(settings.combined_judge_max_checks, 1)
        groups = [asked[start : start + size] for start in range(0, len(asked), size)]
        runs = await asyncio.gather(
            *(self._judge_group(group, run_id, configs, case, target, contexts, limit, shared) for group in groups)
        )
        for found in runs:
            for i, result in found.items():
                results[i] = result
        return results

    async def _judge_group(
        self,
        group: list[int],
        run_id: uuid.UUID,
        configs: list[EvaluatorConfig],
        case: EvalCase,
        target: CallTarget,
        contexts: list[CallContext],
        limit: asyncio.Semaphore,
        shared: dict[str, "asyncio.Future[Any]"],
    ) -> dict[int, Score | Unscored | None]:
        """One group of judged checks of one answer. A check with a stored result uses it (no call); the rest go
        in one combined judge call when there are enough of them, and alone otherwise. A check the combined
        reply did not answer properly is judged again on its own."""
        found: dict[int, Score | Unscored | None] = {}
        pending = []
        for i in group:
            hit = await self._cached(self._key(configs[i], case, target, COMBINED), COMBINED)
            if hit is not None:
                found[i] = hit
            else:
                pending.append(i)
        if len(pending) < max(self._settings.combined_judge_min_checks, 2):
            alone = await asyncio.gather(
                *(self._evaluate_once(configs[i], case, target, contexts[i], limit, shared) for i in pending)
            )
            return found | dict(zip(pending, alone, strict=True))
        joined = "|".join(self._key(configs[i], case, target, COMBINED) for i in pending)
        key = hashlib.sha256(joined.encode()).hexdigest()
        task = shared.get(key)
        if task is None:
            task = shared[key] = asyncio.ensure_future(
                self._combined_call(pending, run_id, configs, case, target, contexts, limit, shared)
            )
        return found | cast("dict[int, Score | Unscored | None]", await task)

    async def _combined_call(
        self,
        pending: list[int],
        run_id: uuid.UUID,
        configs: list[EvaluatorConfig],
        case: EvalCase,
        target: CallTarget,
        contexts: list[CallContext],
        limit: asyncio.Semaphore,
        shared: dict[str, "asyncio.Future[Any]"],
    ) -> dict[int, Score | Unscored | None]:
        """Asks the judge about all `pending` checks in one structured reply. Checks the reply covers are scored
        and stored (per check, under their own keys); on a failed call or a reply that cannot be read, every
        check, and any single check left unanswered, falls back to a call of its own."""
        checks = []
        for i in pending:
            asked = instructions_for(configs[i].config, case)
            assert asked is not None
            checks.append(
                CombinedCheck(configs[i].evaluator_name, configs[i].threshold, asked[0], asked[1], configs[i].config)
            )
        answer = next((answer_text(c.config, case) for c in checks if c.config.get("include_tool_calls")), case.output)
        labels = {"evaluation_run_id": str(run_id), "evaluator": ",".join(c.name for c in checks), COMBINED: "true"}
        context = contexts[pending[0]].model_copy(update={"labels": labels})
        reply: CombinedVerdicts | None = None
        calls: list[LLMResult] = []
        async with limit:
            try:
                reply, calls = await self._gateway.complete_json_target_with_calls(
                    target,
                    [Message(role="user", content=combined_prompt(checks, case, answer))],
                    CombinedVerdicts,
                    CallPurpose.JUDGE,
                    context,
                )
            except AppError as exc:
                log.warning("combined judge call failed, scoring the checks one by one: %s", exc.message)
            except Exception:
                log.warning("combined judge call failed unexpectedly, scoring the checks one by one", exc_info=True)
        verdicts = read_combined(checks, reply) if reply is not None else {}
        usage = self._usage(calls, len(checks))
        found: dict[int, Score | Unscored | None] = {}
        fallback = []
        for i, check in zip(pending, checks, strict=True):
            verdict = verdicts.get(check.name)
            if verdict is None:
                fallback.append(i)
                continue
            result = Score(verdict.value, verdict.passed, verdict.reason, {**verdict.metadata, **usage})
            found[i] = result
            await self._remember(self._key(configs[i], case, target, COMBINED), configs[i].evaluator_name, result)
        again = await asyncio.gather(
            *(self._evaluate_once(configs[i], case, target, contexts[i], limit, shared) for i in fallback)
        )
        return found | dict(zip(fallback, again, strict=True))

    @staticmethod
    def _usage(calls: list[LLMResult], checks: int) -> dict[str, Any]:
        """One check's equal share of a combined call's tokens and cost, so a check is still costed on its own."""
        if not calls:
            return {COMBINED: True}
        costs = [c.cost for c in calls if c.cost is not None]
        total = sum(costs) if costs else None
        usage = {
            "input_tokens": round(share_of(sum(c.input_tokens for c in calls), checks)),
            "output_tokens": round(share_of(sum(c.output_tokens for c in calls), checks)),
            "cost": None if total is None else str(share_of(float(total), checks)),
            "checks_in_call": checks,
        }
        return {COMBINED: True, "usage": usage, "llm_call_id": str(calls[-1].call_id)}

    def _key(self, config: EvaluatorConfig, case: EvalCase, target: CallTarget, mode: str | None = None) -> str:
        """The cache key of one judged check on one answer. A combined result has its own keys: the judge saw a
        different prompt, so its numbers are not interchangeable with a separate call's."""
        extras = cache_extras(config.config, case)
        if mode:
            extras = {**extras, "mode": mode}
        return cache_key(
            config.evaluator_name,
            config.config,
            config.threshold,
            target.profile.litellm_model,
            case.inputs,
            case.output,
            case.expected,
            case.rubric,
            case.context,
            extras or None,
        )

    async def _cached(self, key: str, mode: str | None = None) -> Score | None:
        """The stored result under `key` (recent layer first, then the database), or None."""
        if not self._settings.judge_cache_enabled:
            return None
        found = {"cached": True} | ({COMBINED: True} if mode == COMBINED else {})
        recent = self._recent.get(key)
        if recent is not None:
            return Score(recent.value, recent.passed, recent.reason, found)
        async with self._sessions() as own:
            stored = await JudgeCacheRepository(own).get(key)
            if stored is not None:
                await JudgeCacheRepository(own).count_hit(key)
                await own.commit()
        if stored is None:
            return None
        self._recent.put(key, CachedResult(stored.value, stored.passed, stored.reason))
        return Score(stored.value, stored.passed, stored.reason, found)

    async def _remember(self, key: str, name: str, result: Score) -> None:
        """Stores a result that scored. A failed or unscored call is never stored."""
        if not self._settings.judge_cache_enabled:
            return
        self._recent.put(key, CachedResult(result.value, result.passed, result.reason))
        async with self._sessions() as own:
            await JudgeCacheRepository(own).put(key, name, result.value, result.passed, result.reason)
            await own.commit()

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
        key = self._key(config, case, target)
        task = shared.get(key)
        if task is None:
            task = shared[key] = asyncio.ensure_future(self._judge_cached(key, config, case, target, context, limit))
            return await task
        result = await task
        if isinstance(result, Unscored):
            return await self._evaluate(config, case, target, context, limit)
        return result

    async def _judge_cached(
        self,
        key: str,
        config: EvaluatorConfig,
        case: EvalCase,
        target: CallTarget,
        context: CallContext,
        limit: asyncio.Semaphore,
    ) -> Score | Unscored | None:
        """The stored result for this exact content when there is one (no judge call, no cost); otherwise the
        judge is called and a result that scored is stored. A failed or unscored call is never stored."""
        if not self._settings.judge_cache_enabled or instructions_for(config.config, case) is None:
            return await self._evaluate(config, case, target, context, limit)
        stored = await self._cached(key)
        if stored is not None:
            return stored
        result = await self._evaluate(config, case, target, context, limit)
        if isinstance(result, Score):
            await self._remember(key, config.evaluator_name, result)
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
        if config.config.get("kind") == CODE:
            return await self._run_code(config, case)
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

    async def _run_code(self, config: EvaluatorConfig, case: EvalCase) -> Score | Unscored:
        """A custom code check, run in the sandbox. A check that errors, times out or cannot be reached is
        shown as unscored with the reason, never as a pass and never as a zero (ADR 0019)."""
        settings = self._settings
        if not is_enabled(settings, CODE_CHECKS):
            return Unscored(CHECK_BROKEN.format(why="custom code checks are switched off on this server."))
        limits = SandboxLimits(
            wall_s=settings.sandbox_wall_s,
            cpu_s=settings.sandbox_cpu_s,
            memory_mb=settings.sandbox_memory_mb,
            output_chars=settings.sandbox_output_chars,
        )
        request = SandboxRequest(
            code=str(config.config.get("code") or ""),
            case={"inputs": case.inputs, "output": case.output, "expected": case.expected, "rubric": case.rubric},
        )
        result = await self._sandbox.run(request, limits)
        if not result.ok or result.score is None:
            return Unscored(CHECK_BROKEN.format(why=result.error or result.reason or "no result"))
        passed = result.passed if result.passed is not None else result.score >= config.threshold
        return Score(result.score, passed, result.reason or ("Passed." if passed else "Failed."))

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
        case = self._case(item, row, spec)
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
