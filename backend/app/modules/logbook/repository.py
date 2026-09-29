"""
Logbook queries. Read-only, and built on the records the app already keeps:
`test_case_runs` (one row per model answer), the scores of each experiment's newest
finished scoring run (the same rule Results uses), `dataset_items` (input and golden
answer), `prompt_versions`, and `llm_calls` (every model call, whatever its purpose).

`answers()` is the one definition of a logbook row, as a subquery. Filters, sorting,
paging, the CSV export and the analysis all read that subquery, so they can never disagree.
A case passes when every check that applies passed; a successful call with no applicable
check counts as passed with quality 1, as in Results; a call that never finished has no
verdict. Long texts are cut to a preview in SQL, so a page of rows stays small even when an
input file is large.
"""

import uuid
from typing import Any

from sqlalchemy import Select, Subquery, and_, case, cast, func, or_, select, true
from sqlalchemy.dialects.postgresql import ARRAY, distinct_on
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.sqltypes import String, Text

from app.modules.datasets.models import DatasetItem
from app.modules.engine.models import Experiment, TestCaseRun
from app.modules.engine.schemas import RunStatus
from app.modules.evaluation.models import EvaluationRun, Score
from app.modules.evaluation.schemas import EvaluationRunStatus
from app.modules.gateway.models import LLMCall
from app.modules.logbook.schemas import AnswerFilters, AnswerSort, CallFilters, SortOrder
from app.modules.prompts.models import PromptVersion

PREVIEW = 400
LONG_PREVIEW = 1500
GOLDEN_MATCH_CHECK = "field_match"


def _like(text: str) -> str:
    return "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def answers(project_id: uuid.UUID) -> Subquery:
    latest = (
        select(EvaluationRun.experiment_id.label("experiment_id"), EvaluationRun.id.label("run_id"))
        .ext(distinct_on(EvaluationRun.experiment_id))
        .where(EvaluationRun.status == EvaluationRunStatus.COMPLETED)
        .order_by(EvaluationRun.experiment_id, EvaluationRun.id.desc())
        .subquery()
    )
    scored = (
        select(
            Score.experiment_id.label("experiment_id"),
            Score.test_case_run_id.label("run_id"),
            func.bool_and(Score.passed).label("passed"),
            (func.sum(Score.value * Score.weight) / func.nullif(func.sum(Score.weight), 0)).label("quality"),
            func.array_agg(Score.evaluator_name).filter(Score.passed.is_(False)).label("failed"),
            func.max(Score.value).filter(Score.evaluator_name == GOLDEN_MATCH_CHECK).label("golden_match"),
        )
        .join(latest, and_(Score.experiment_id == latest.c.experiment_id, Score.evaluation_run_id == latest.c.run_id))
        .group_by(Score.experiment_id, Score.test_case_run_id)
        .subquery()
    )
    ok = TestCaseRun.status == RunStatus.SUCCEEDED
    inputs_text = cast(DatasetItem.inputs, Text)
    query = (
        select(
            TestCaseRun.id.label("run_id"),
            TestCaseRun.experiment_id.label("experiment_id"),
            Experiment.name.label("experiment"),
            TestCaseRun.created_at.label("created_at"),
            TestCaseRun.prompt_version_id.label("prompt_version_id"),
            PromptVersion.version.label("prompt_version"),
            TestCaseRun.model.label("model"),
            TestCaseRun.provider.label("provider"),
            TestCaseRun.run_number.label("run_number"),
            TestCaseRun.dataset_item_id.label("dataset_item_id"),
            (DatasetItem.position + 1).label("case_number"),
            DatasetItem.source.label("source"),
            DatasetItem.category.label("category"),
            TestCaseRun.status.label("status"),
            case((scored.c.passed.is_not(None), scored.c.passed), (ok, true()), else_=None).label("passed"),
            case((scored.c.quality.is_not(None), scored.c.quality), (ok, 1.0), else_=None).label("quality"),
            scored.c.golden_match.label("golden_match"),
            scored.c.failed.label("failed"),
            func.left(inputs_text, PREVIEW).label("input_preview"),
            func.left(DatasetItem.expected_output, LONG_PREVIEW).label("golden_answer"),
            func.left(TestCaseRun.raw_output, LONG_PREVIEW).label("output_preview"),
            func.coalesce(TestCaseRun.error_message, TestCaseRun.error_type).label("error"),
            TestCaseRun.input_tokens.label("input_tokens"),
            TestCaseRun.output_tokens.label("output_tokens"),
            TestCaseRun.cost.label("cost"),
            TestCaseRun.latency_ms.label("latency_ms"),
            TestCaseRun.params.label("params"),
            TestCaseRun.attempts.label("attempts"),
            inputs_text.label("input_full"),
            DatasetItem.expected_output.label("golden_full"),
            TestCaseRun.raw_output.label("output_full"),
        )
        .join(Experiment, Experiment.id == TestCaseRun.experiment_id)
        .join(DatasetItem, DatasetItem.id == TestCaseRun.dataset_item_id)
        .join(PromptVersion, PromptVersion.id == TestCaseRun.prompt_version_id)
        .outerjoin(scored, and_(scored.c.experiment_id == TestCaseRun.experiment_id, scored.c.run_id == TestCaseRun.id))
        .where(Experiment.project_id == project_id)
    )
    return query.subquery("answers")


def filtered(a: Subquery, filters: AnswerFilters) -> Select[Any]:
    query = select(a)
    if filters.experiment_ids:
        query = query.where(a.c.experiment_id.in_(filters.experiment_ids))
    if filters.prompt_version_ids:
        query = query.where(a.c.prompt_version_id.in_(filters.prompt_version_ids))
    if filters.models:
        query = query.where(a.c.model.in_(filters.models))
    if filters.providers:
        query = query.where(a.c.provider.in_(filters.providers))
    if filters.statuses:
        query = query.where(a.c.status.in_(filters.statuses))
    if filters.sources:
        query = query.where(a.c.source.in_(filters.sources))
    if filters.categories:
        query = query.where(a.c.category.in_(filters.categories))
    if filters.failed_checks:
        query = query.where(a.c.failed.overlap(cast(filters.failed_checks, ARRAY(String))))
    if filters.passed is not None:
        query = query.where(a.c.passed.is_(filters.passed))
    if filters.run_number is not None:
        query = query.where(a.c.run_number == filters.run_number)
    if filters.date_from is not None:
        query = query.where(a.c.created_at >= filters.date_from)
    if filters.date_to is not None:
        query = query.where(a.c.created_at <= filters.date_to)
    if filters.q:
        pattern = _like(filters.q)
        query = query.where(
            or_(
                a.c.input_full.ilike(pattern, escape="\\"),
                a.c.golden_full.ilike(pattern, escape="\\"),
                a.c.output_full.ilike(pattern, escape="\\"),
                a.c.model.ilike(pattern, escape="\\"),
                a.c.experiment.ilike(pattern, escape="\\"),
            )
        )
    return query


def sort_column(a: Subquery, sort: AnswerSort) -> Any:
    return {
        AnswerSort.TIME: a.c.created_at,
        AnswerSort.EXPERIMENT: a.c.experiment,
        AnswerSort.VERSION: a.c.prompt_version,
        AnswerSort.MODEL: a.c.model,
        AnswerSort.CASE: a.c.case_number,
        AnswerSort.PASSED: a.c.passed,
        AnswerSort.QUALITY: a.c.quality,
        AnswerSort.GOLDEN_MATCH: a.c.golden_match,
        AnswerSort.COST: a.c.cost,
        AnswerSort.LATENCY: a.c.latency_ms,
        AnswerSort.TOKENS: func.coalesce(a.c.input_tokens, 0) + func.coalesce(a.c.output_tokens, 0),
    }[sort]


def ordered(query: Select[Any], a: Subquery, sort: AnswerSort, order: SortOrder) -> Select[Any]:
    column = sort_column(a, sort)
    direction = column.asc().nulls_last() if order is SortOrder.ASC else column.desc().nulls_last()
    return query.order_by(direction, a.c.created_at.desc(), a.c.run_id.desc())


def call_rows(project_id: uuid.UUID) -> Subquery:
    query = (
        select(
            LLMCall.id.label("id"),
            LLMCall.created_at.label("created_at"),
            LLMCall.purpose.label("purpose"),
            LLMCall.status.label("status"),
            LLMCall.provider.label("provider"),
            LLMCall.model.label("model"),
            LLMCall.experiment_id.label("experiment_id"),
            Experiment.name.label("experiment"),
            LLMCall.labels["step"].as_string().label("step"),
            LLMCall.input_tokens.label("input_tokens"),
            LLMCall.output_tokens.label("output_tokens"),
            LLMCall.cost.label("cost"),
            LLMCall.latency_ms.label("latency_ms"),
            LLMCall.ttft_ms.label("ttft_ms"),
            LLMCall.attempts.label("attempts"),
            func.coalesce(LLMCall.error_message, LLMCall.error_type).label("error"),
            func.left(cast(LLMCall.request_messages, Text), PREVIEW).label("request_preview"),
            func.left(LLMCall.output_text, PREVIEW).label("response_preview"),
            cast(LLMCall.request_messages, Text).label("request_full"),
            LLMCall.output_text.label("response_full"),
        )
        .outerjoin(Experiment, Experiment.id == LLMCall.experiment_id)
        .where(LLMCall.project_id == project_id)
    )
    return query.subquery("calls")


def filtered_calls(c: Subquery, filters: CallFilters) -> Select[Any]:
    query = select(c)
    if filters.experiment_ids:
        query = query.where(c.c.experiment_id.in_(filters.experiment_ids))
    if filters.purposes:
        query = query.where(c.c.purpose.in_(filters.purposes))
    if filters.statuses:
        query = query.where(c.c.status.in_(filters.statuses))
    if filters.models:
        query = query.where(c.c.model.in_(filters.models))
    if filters.providers:
        query = query.where(c.c.provider.in_(filters.providers))
    if filters.date_from is not None:
        query = query.where(c.c.created_at >= filters.date_from)
    if filters.date_to is not None:
        query = query.where(c.c.created_at <= filters.date_to)
    if filters.q:
        pattern = _like(filters.q)
        query = query.where(
            or_(c.c.request_full.ilike(pattern, escape="\\"), c.c.response_full.ilike(pattern, escape="\\"))
        )
    return query


class LogbookRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def rows(self, query: Any) -> list[Any]:
        return list((await self._session.execute(query)).mappings().all())

    async def count(self, query: Any) -> int:
        total = await self._session.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
        return int(total or 0)

    async def scalar_list(self, query: Any) -> list[Any]:
        return list((await self._session.scalars(query)).all())

    async def execute(self, query: Any) -> list[Any]:
        return list((await self._session.execute(query)).all())

    async def one_run(self, project_id: uuid.UUID, experiment_id: uuid.UUID, run_id: uuid.UUID) -> Any | None:
        query = (
            select(TestCaseRun, DatasetItem)
            .join(DatasetItem, DatasetItem.id == TestCaseRun.dataset_item_id)
            .join(Experiment, Experiment.id == TestCaseRun.experiment_id)
            .where(
                Experiment.project_id == project_id,
                TestCaseRun.experiment_id == experiment_id,
                TestCaseRun.id == run_id,
            )
        )
        return (await self._session.execute(query)).first()
