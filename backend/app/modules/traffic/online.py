"""
Online scoring (ADR 0032): the project's own checks, run on a sample of live traffic.

The checks are the evaluators of the project's current evaluator set, run through the evaluation module's own pieces
(its rule functions and its judge), never copies of them. Which traces are scored is decided by a stable hash of the
trace id (`in_sample`): rule checks are free and run on `rule_sample_rate` of traffic; judge checks cost money and run
on `judge_sample_rate` of it, never beyond the project's monthly judge limit. Each scored trace gets one quality number
and a pass or fail, and the daily score line is a grouped query over those. A call that failed counts as a failure,
as in a test run. Custom code checks are not run on live traffic (they would need the sandbox per trace).
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.container import Container
from app.core.errors import AppError
from app.core.ids import uuid7
from app.core.security import utcnow
from app.modules.evaluation.domain import EvalCase, Score
from app.modules.evaluation.models import EvaluatorConfig
from app.modules.evaluation.plugins.deepeval_adapter import instructions_for, judge
from app.modules.evaluation.plugins.rules import RULES
from app.modules.evaluation.repository import EvaluatorRepository
from app.modules.gateway.dependencies import build_gateway
from app.modules.gateway.schemas import CallContext
from app.modules.generator.models import TaskSpecRecord
from app.modules.generator.schemas import TaskSpec, TaskSpecStatus
from app.modules.registry.schemas import CallTarget
from app.modules.registry.service import RegistryService
from app.modules.traffic.config import effective_config
from app.modules.traffic.domain import CheckResult, combine_checks, in_sample, judge_allowance, month_start
from app.modules.traffic.models import TrafficTrace
from app.modules.traffic.repository import TrafficRepository

log = logging.getLogger(__name__)
DEEPEVAL = "deepeval"
CALL_ERROR = "call_error"
MAX_BATCHES = 20


@dataclass
class Plan:
    configs: list[EvaluatorConfig]
    spec: TaskSpec
    target: CallTarget | None

    @property
    def has_judges(self) -> bool:
        return self.target is not None and any(c.config.get("kind") == DEEPEVAL for c in self.configs)


@dataclass
class ProcessSummary:
    scored: int = 0
    judged: int = 0
    sampled_out: int = 0
    over_judge_limit: int = 0
    reason: str | None = None


class OnlineScoringService:
    def __init__(self, session: AsyncSession, container: Container) -> None:
        self._session = session
        self._container = container
        self._settings = container.settings
        self._repo = TrafficRepository(session)
        self._evaluators = EvaluatorRepository(session)
        self._registry = RegistryService(session, container)

    async def _plan(self, project_id: uuid.UUID) -> Plan | None:
        """The project's newest evaluator set, the newest confirmed Task Spec and the judge model, or None when the
        project has no checks to run yet."""
        evaluator_set = await self._evaluators.project_set(project_id)
        if evaluator_set is None:
            return None
        versions = await self._evaluators.versions(evaluator_set.id)
        if not versions:
            return None
        record = await self._session.scalar(
            select(TaskSpecRecord)
            .where(TaskSpecRecord.project_id == project_id, TaskSpecRecord.status == TaskSpecStatus.CONFIRMED)
            .order_by(TaskSpecRecord.id.desc())
            .limit(1)
        )
        if record is None:
            return None
        configs = await self._evaluators.configs(versions[0].id)
        target: CallTarget | None = None
        choice = versions[0].judge
        if choice:
            try:
                target = await self._registry.call_target(
                    project_id, uuid.UUID(str(choice["credential_id"])), str(choice["model"])
                )
            except AppError:
                log.warning("judge model unavailable for live scoring in project %s", project_id)
        return Plan(
            [c for c in configs if c.config.get("kind") != "code"], TaskSpec.model_validate(record.spec), target
        )

    async def process(self, project_id: uuid.UUID) -> ProcessSummary:
        """Scores traces that have not been looked at yet, a batch at a time, committing after each batch."""
        summary = ProcessSummary()
        config = effective_config(await self._repo.config(project_id), self._settings)
        if not config.scoring_enabled:
            summary.reason = "Online scoring is switched off for this project."
            return summary
        plan = await self._plan(project_id)
        if plan is None:
            await self._mark_without_checks(project_id)
            summary.reason = "This project has no checks yet. Create a test set and its checks first."
            return summary
        await self._repo.reset_states(project_id, ["no_checks"])
        batch_size = self._settings.traffic_score_batch
        for _ in range(MAX_BATCHES):
            fresh = await self._repo.new_traces(project_id, batch_size)
            if not fresh:
                break
            await self._sample(
                project_id,
                fresh,
                config.rule_sample_rate,
                config.judge_sample_rate,
                config.judge_monthly_limit,
                plan,
                summary,
            )
            await self._session.commit()
            for trace in await self._repo.claim_queued(project_id, batch_size):
                await self._score(trace, plan, summary)
            await self._session.commit()
        return summary

    async def _mark_without_checks(self, project_id: uuid.UUID) -> None:
        while fresh := await self._repo.new_traces(project_id, 1_000):
            await self._repo.set_states([trace_id for trace_id, _ in fresh], "no_checks")
            await self._session.commit()

    async def _sample(
        self,
        project_id: uuid.UUID,
        fresh: list[tuple[uuid.UUID, str]],
        rule_rate: float,
        judge_rate: float,
        monthly_limit: int,
        plan: Plan,
        summary: ProcessSummary,
    ) -> None:
        by_rule = {tid for tid, _ in fresh if in_sample(str(tid), rule_rate, "rule")}
        wants_judge = [tid for tid, _ in fresh if plan.has_judges and in_sample(str(tid), judge_rate, "judge")]
        used = await self._repo.judged_since(project_id, month_start(utcnow()))
        allowed = judge_allowance(monthly_limit, used, len(wants_judge))
        judged = set(wants_judge[:allowed])
        summary.over_judge_limit += len(wants_judge) - allowed
        queued_judged = list(judged)
        queued_plain = [tid for tid in by_rule if tid not in judged]
        out = [tid for tid, _ in fresh if tid not in judged and tid not in by_rule]
        await self._repo.set_states(queued_judged, "queued", judge_sampled=True)
        await self._repo.set_states(queued_plain, "queued")
        await self._repo.set_states(out, "sampled_out")
        summary.sampled_out += len(out)

    async def _score(self, trace: TrafficTrace, plan: Plan, summary: ProcessSummary) -> None:
        now = utcnow()
        if trace.status == "error":
            await self._finish(
                trace,
                [CheckResult(CALL_ERROR, 0.0, False, True, 1.0)],
                {CALL_ERROR: trace.error_message or "The call failed."},
                now,
                False,
                summary,
            )
            return
        variable = plan.spec.input_variables[0] if plan.spec.input_variables else "input"
        case = EvalCase(
            inputs={variable: trace.input_text},
            output=trace.output_text,
            expected=None,
            rubric=None,
            task_spec=plan.spec,
        )
        results: list[CheckResult] = []
        reasons: dict[str, str] = {}
        limit = asyncio.Semaphore(self._settings.judge_concurrency)
        gateway = build_gateway(self._container, self._registry)
        any_judged = False

        async def run(config: EvaluatorConfig) -> None:
            nonlocal any_judged
            is_judge = config.config.get("kind") == DEEPEVAL
            score: Score | None
            if is_judge:
                if not trace.judge_sampled or plan.target is None or instructions_for(config.config, case) is None:
                    return
                context = CallContext(
                    project_id=trace.project_id, labels={"traffic": "true", "evaluator": config.evaluator_name}
                )
                async with limit:
                    try:
                        score = await judge(
                            gateway, plan.target, context, config.evaluator_name, config.config, config.threshold, case
                        )
                    except AppError as error:
                        log.warning("live judge %s failed: %s", config.evaluator_name, error.message)
                        return
                    except Exception:
                        log.warning("live judge %s failed unexpectedly", config.evaluator_name, exc_info=True)
                        return
                any_judged = any_judged or score is not None
            else:
                rule = RULES.get(config.evaluator_name)
                score = rule(case, config.config, config.threshold) if rule else None
            if score is not None:
                results.append(
                    CheckResult(
                        config.evaluator_name, score.value, score.passed, config.required, config.weight, is_judge
                    )
                )
                reasons[config.evaluator_name] = score.reason

        await asyncio.gather(*(run(config) for config in plan.configs))
        await self._finish(trace, results, reasons, now, any_judged, summary)

    async def _finish(
        self,
        trace: TrafficTrace,
        results: list[CheckResult],
        reasons: dict[str, str],
        now: datetime,
        judged: bool,
        summary: ProcessSummary,
    ) -> None:
        quality, passed = combine_checks(results)
        rows: list[dict[str, Any]] = [
            {
                "id": uuid7(),
                "trace_id": trace.id,
                "evaluator_name": r.name,
                "value": r.value,
                "passed": r.passed,
                "judged": r.judged,
                "required": r.required,
                "weight": r.weight,
                "reason": reasons.get(r.name, "")[:1000],
            }
            for r in results
        ]
        await self._repo.save_scores(rows)
        await self._repo.finish_trace(
            trace.id,
            {
                "score_state": "scored" if results else "sampled_out",
                "quality": quality,
                "passed": passed,
                "scored_at": now,
                "judged": judged,
                "judged_at": now if judged else None,
            },
        )
        if results:
            summary.scored += 1
            summary.judged += int(judged)
        else:
            summary.sampled_out += 1
