"""
Logbook use cases: the filtered, sortable table of every model answer, one answer in full
next to the same case's other answers, the raw model calls, the numbers behind the analysis
charts, a CSV of whatever the filters select, and the values the filter controls offer.
Everything is read from existing records (see repository.py); nothing is copied or stored.
"""

import csv
import io
import uuid
from typing import Any

from sqlalchemy import cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.sqltypes import Float

from app.core.errors import NotFound
from app.modules.engine.models import Experiment
from app.modules.engine.schemas import RunStatus
from app.modules.evaluation.models import Score
from app.modules.gateway.models import LLMCall
from app.modules.logbook.repository import (
    LogbookRepository,
    answers,
    call_rows,
    filtered,
    filtered_calls,
    ordered,
)
from app.modules.logbook.schemas import (
    AnalysisOut,
    AnswerDetail,
    AnswerFilters,
    AnswerPage,
    AnswerRow,
    AnswerSort,
    CallDetail,
    CallFilters,
    CallPage,
    CallRow,
    CheckCount,
    ExperimentOption,
    GroupStats,
    LogOptions,
    ScoreDetail,
    SiblingAnswer,
    SortOrder,
    Totals,
    VersionOption,
)
from app.modules.prompts.models import PromptVersion

ANSWER_NOT_FOUND = "This answer doesn't exist in this project."
CALL_NOT_FOUND = "This model call doesn't exist in this project."
MAX_PAGE = 500
EXPORT_LIMIT = 50_000


def answer_row(row: Any) -> AnswerRow:
    params = row["params"] or {}
    return AnswerRow(
        run_id=row["run_id"],
        experiment_id=row["experiment_id"],
        experiment=row["experiment"],
        created_at=row["created_at"],
        prompt_version_id=row["prompt_version_id"],
        prompt_version=row["prompt_version"],
        model=row["model"],
        provider=row["provider"],
        run_number=row["run_number"],
        case_number=row["case_number"],
        source=row["source"].value if hasattr(row["source"], "value") else str(row["source"]),
        category=row["category"],
        status=row["status"],
        passed=row["passed"],
        quality=row["quality"],
        golden_match=row["golden_match"],
        failed_checks=sorted(set(row["failed"] or [])),
        input_preview=row["input_preview"] or "",
        golden_answer=row["golden_answer"],
        output_preview=row["output_preview"],
        error=row["error"],
        input_tokens=row["input_tokens"],
        output_tokens=row["output_tokens"],
        cost=row["cost"],
        latency_ms=row["latency_ms"],
        temperature=params.get("temperature"),
        max_tokens=params.get("max_tokens"),
        attempts=row["attempts"],
    )


class LogbookService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = LogbookRepository(session)

    async def options(self, project_id: uuid.UUID) -> LogOptions:
        a = answers(project_id)
        experiments = await self._repo.execute(
            select(
                Experiment.id,
                Experiment.name,
                Experiment.created_at,
                Experiment.prompt_version_id,
                PromptVersion.version,
            )
            .join(PromptVersion, PromptVersion.id == Experiment.prompt_version_id)
            .where(Experiment.project_id == project_id)
            .order_by(Experiment.id.desc())
        )
        versions = await self._repo.execute(
            select(PromptVersion.id, PromptVersion.version)
            .where(PromptVersion.id.in_(select(a.c.prompt_version_id)))
            .order_by(PromptVersion.version)
        )
        models = await self._repo.scalar_list(select(a.c.model).distinct().order_by(a.c.model))
        providers = await self._repo.scalar_list(select(a.c.provider).distinct().order_by(a.c.provider))
        categories = await self._repo.scalar_list(select(a.c.category).distinct().order_by(a.c.category))
        checks = await self._repo.scalar_list(
            select(Score.evaluator_name)
            .join(Experiment, Experiment.id == Score.experiment_id)
            .where(Experiment.project_id == project_id)
            .distinct()
            .order_by(Score.evaluator_name)
        )
        return LogOptions(
            experiments=[
                ExperimentOption(id=i, name=n, created_at=c, prompt_version_id=v, prompt_version=number)
                for i, n, c, v, number in experiments
            ],
            prompt_versions=[VersionOption(id=i, version=v) for i, v in versions],
            models=models,
            providers=providers,
            categories=categories,
            checks=checks,
        )

    async def answers(
        self,
        project_id: uuid.UUID,
        filters: AnswerFilters,
        sort: AnswerSort,
        order: SortOrder,
        offset: int,
        limit: int,
    ) -> AnswerPage:
        a = answers(project_id)
        base = filtered(a, filters)
        total = await self._repo.count(base)
        rows = await self._repo.rows(ordered(base, a, sort, order).offset(offset).limit(min(limit, MAX_PAGE)))
        return AnswerPage(items=[answer_row(r) for r in rows], total=total, offset=offset, limit=limit)

    async def answer(self, project_id: uuid.UUID, experiment_id: uuid.UUID, run_id: uuid.UUID) -> AnswerDetail:
        found = await self._repo.one_run(project_id, experiment_id, run_id)
        if found is None:
            raise NotFound(ANSWER_NOT_FOUND)
        run, item = found
        a = answers(project_id)
        same_case = await self._repo.rows(
            select(a)
            .where(a.c.experiment_id == experiment_id, a.c.dataset_item_id == item.id)
            .order_by(a.c.model, a.c.run_number)
        )
        row = next(r for r in same_case if r["run_id"] == run_id)
        scores = await self._repo.scalar_list(
            select(Score)
            .where(Score.experiment_id == experiment_id, Score.test_case_run_id == run_id)
            .order_by(Score.created_at)
        )
        latest = {}
        for score in scores:
            latest[(score.evaluation_run_id, score.evaluator_name)] = score
        newest = max((s.evaluation_run_id for s in scores), default=None)
        return AnswerDetail(
            row=answer_row(row),
            inputs=item.inputs,
            golden_answer=item.expected_output,
            rubric=item.rubric,
            output=run.raw_output,
            rendered_system_prompt=run.rendered_system_prompt,
            rendered_user_prompt=run.rendered_user_prompt,
            finish_reason=run.finish_reason,
            params=run.params,
            scores=[
                ScoreDetail(
                    evaluator=s.evaluator_name,
                    value=s.value,
                    passed=s.passed,
                    required=s.required,
                    weight=s.weight,
                    reason=s.reason,
                )
                for (run_id_, _), s in latest.items()
                if run_id_ == newest
            ],
            siblings=[
                SiblingAnswer(
                    run_id=r["run_id"],
                    model=r["model"],
                    run_number=r["run_number"],
                    output=r["output_preview"],
                    error=r["error"],
                    passed=r["passed"],
                    quality=r["quality"],
                    cost=r["cost"],
                    latency_ms=r["latency_ms"],
                )
                for r in same_case
                if r["run_id"] != run_id
            ],
        )

    async def analysis(self, project_id: uuid.UUID, filters: AnswerFilters) -> AnalysisOut:
        a = filtered(answers(project_id), filters).subquery("f")
        judged = func.count().filter(a.c.passed.is_not(None))
        groups = await self._repo.execute(
            select(
                a.c.prompt_version,
                a.c.model,
                func.count(),
                func.count().filter(a.c.passed.is_(True)),
                judged,
                func.avg(a.c.quality),
                func.avg(a.c.golden_match),
                func.count().filter(a.c.status == RunStatus.FAILED),
                func.sum(a.c.cost),
                func.count().filter(a.c.cost.is_(None)),
                func.avg(a.c.latency_ms),
                func.percentile_cont(0.5).within_group(cast(a.c.latency_ms, Float)),
                func.percentile_cont(0.9).within_group(cast(a.c.latency_ms, Float)),
                func.coalesce(func.sum(a.c.input_tokens), 0),
                func.coalesce(func.sum(a.c.output_tokens), 0),
            )
            .group_by(a.c.prompt_version, a.c.model)
            .order_by(a.c.prompt_version, a.c.model)
        )
        stats = [
            GroupStats(
                prompt_version=version,
                model=model,
                answers=count,
                passed=passed,
                pass_rate=passed / judged_count if judged_count else None,
                quality=quality,
                golden_match=golden,
                failed_calls=failed,
                cost=cost if not unknown else None,
                unknown_price_answers=unknown,
                avg_latency_ms=avg_latency,
                p50_latency_ms=p50,
                p90_latency_ms=p90,
                input_tokens=int(tokens_in),
                output_tokens=int(tokens_out),
            )
            for (
                version,
                model,
                count,
                passed,
                judged_count,
                quality,
                golden,
                failed,
                cost,
                unknown,
                avg_latency,
                p50,
                p90,
                tokens_in,
                tokens_out,
            ) in groups
        ]
        a_checks = select(func.unnest(a.c.failed).label("name")).select_from(a).subquery("c")
        counted = await self._repo.execute(
            select(a_checks.c.name, func.count())
            .group_by(a_checks.c.name)
            .order_by(func.count().desc(), a_checks.c.name)
        )
        totals_row = (
            await self._repo.execute(
                select(
                    func.count(),
                    func.count(func.distinct(a.c.experiment_id)),
                    func.count(func.distinct(a.c.model)),
                    func.count().filter(a.c.passed.is_(True)),
                    func.count().filter(a.c.status == RunStatus.FAILED),
                    func.sum(a.c.cost),
                    func.count().filter(a.c.cost.is_(None)),
                    func.coalesce(func.sum(a.c.input_tokens), 0),
                    func.coalesce(func.sum(a.c.output_tokens), 0),
                ).select_from(a)
            )
        )[0]
        answers_n, experiments_n, models_n, passed_n, failed_n, cost, unknown, tokens_in, tokens_out = totals_row
        return AnalysisOut(
            totals=Totals(
                answers=answers_n,
                experiments=experiments_n,
                models=models_n,
                passed=passed_n,
                failed_calls=failed_n,
                cost=cost if not unknown else None,
                unknown_price_answers=unknown,
                input_tokens=int(tokens_in),
                output_tokens=int(tokens_out),
            ),
            groups=stats,
            failed_checks=[CheckCount(check=name, failures=n) for name, n in counted],
        )

    async def export_csv(
        self, project_id: uuid.UUID, filters: AnswerFilters, sort: AnswerSort, order: SortOrder
    ) -> str:
        a = answers(project_id)
        query = ordered(filtered(a, filters), a, sort, order).limit(EXPORT_LIMIT)
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            [
                "time", "experiment", "prompt_version", "model", "provider", "run", "case", "source", "category",
                "status", "passed", "quality", "golden_match", "failed_checks", "input", "golden_answer", "output",
                "error", "input_tokens", "output_tokens", "cost", "latency_ms", "temperature", "max_tokens",
            ]
        )  # fmt: skip
        for raw in await self._repo.rows(query):
            r = answer_row(raw)
            writer.writerow(
                [
                    r.created_at.isoformat(), r.experiment, r.prompt_version, r.model, r.provider, r.run_number,
                    r.case_number, r.source, r.category, r.status.value, r.passed, r.quality, r.golden_match,
                    "; ".join(r.failed_checks), r.input_preview, r.golden_answer, r.output_preview, r.error,
                    r.input_tokens, r.output_tokens, r.cost, r.latency_ms, r.temperature, r.max_tokens,
                ]
            )  # fmt: skip
        return buffer.getvalue()

    async def calls(self, project_id: uuid.UUID, filters: CallFilters, offset: int, limit: int) -> CallPage:
        c = call_rows(project_id)
        base = filtered_calls(c, filters)
        total = await self._repo.count(base)
        rows = await self._repo.rows(
            base.order_by(c.c.created_at.desc(), c.c.id.desc()).offset(offset).limit(min(limit, MAX_PAGE))
        )
        return CallPage(items=[call_row(r) for r in rows], total=total, offset=offset, limit=limit)

    async def call(self, project_id: uuid.UUID, call_id: uuid.UUID) -> CallDetail:
        c = call_rows(project_id)
        rows = await self._repo.rows(select(c).where(c.c.id == call_id))
        full = await self._repo.scalar_list(
            select(LLMCall).where(LLMCall.id == call_id, LLMCall.project_id == project_id)
        )
        if not rows or not full:
            raise NotFound(CALL_NOT_FOUND)
        model = full[0]
        return CallDetail(
            row=call_row(rows[0]),
            params=model.params,
            labels=model.labels,
            request_messages=model.request_messages,
            output_text=model.output_text,
            finish_reason=model.finish_reason,
            trace_id=model.trace_id,
        )


def call_row(row: Any) -> CallRow:
    return CallRow(
        id=row["id"],
        created_at=row["created_at"],
        purpose=row["purpose"],
        status=row["status"],
        provider=row["provider"],
        model=row["model"],
        experiment_id=row["experiment_id"],
        experiment=row["experiment"],
        step=row["step"],
        input_tokens=row["input_tokens"],
        output_tokens=row["output_tokens"],
        cost=row["cost"],
        latency_ms=row["latency_ms"],
        ttft_ms=row["ttft_ms"],
        attempts=row["attempts"],
        error=row["error"],
        request_preview=row["request_preview"] or "",
        response_preview=row["response_preview"],
    )
