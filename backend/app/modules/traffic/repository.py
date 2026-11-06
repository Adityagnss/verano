"""
Traffic data access. Every query is scoped to one project and runs on an index; rows are written in batches
(one multi-row INSERT per few hundred traces, duplicates skipped by the database), and the daily score line is one
grouped query, not a query per day.
"""

import uuid
from collections.abc import Sequence
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import Select, delete, func, not_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.pagination import PageParams
from app.modules.traffic.models import (
    Alert,
    AlertChannel,
    AlertRule,
    TrafficConfig,
    TrafficIngestDay,
    TrafficScore,
    TrafficToken,
    TrafficTrace,
)
from app.modules.traffic.schemas import TraceFilter

INSERT_CHUNK = 500
INGEST_COUNTERS = frozenset({"accepted", "ignored", "dropped_rate", "dropped_size", "rejected_requests"})
PURGE_BATCH = 5_000


class TrafficRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------------------------------- settings

    async def config(self, project_id: uuid.UUID) -> TrafficConfig | None:
        return await self._session.get(TrafficConfig, project_id, populate_existing=True)

    async def save_config(self, row: TrafficConfig) -> None:
        self._session.add(row)
        await self._session.flush()

    # ------------------------------------------------------------------------------------------- tokens

    async def add(self, row: TrafficToken | AlertChannel | AlertRule | Alert) -> None:
        self._session.add(row)
        await self._session.flush()

    async def tokens(self, project_id: uuid.UUID) -> list[TrafficToken]:
        query = select(TrafficToken).where(TrafficToken.project_id == project_id).order_by(TrafficToken.id.desc())
        return list((await self._session.scalars(query)).all())

    async def token(self, project_id: uuid.UUID, token_id: uuid.UUID) -> TrafficToken | None:
        query = select(TrafficToken).where(TrafficToken.project_id == project_id, TrafficToken.id == token_id)
        return await self._session.scalar(query.execution_options(populate_existing=True))

    async def token_by_hash(self, token_hash: str) -> TrafficToken | None:
        query = select(TrafficToken).where(TrafficToken.token_hash == token_hash, TrafficToken.revoked_at.is_(None))
        return await self._session.scalar(query)

    async def touch_token(self, token_id: uuid.UUID, now: datetime, older_than: timedelta) -> None:
        await self._session.execute(
            update(TrafficToken)
            .where(
                TrafficToken.id == token_id,
                (TrafficToken.last_used_at.is_(None)) | (TrafficToken.last_used_at < now - older_than),
            )
            .values(last_used_at=now)
        )

    # ------------------------------------------------------------------------------------------- traces

    async def insert_traces(self, rows: list[dict[str, Any]]) -> int:
        """Stores the rows in batches and returns how many were new (a repeat of a stored trace is skipped)."""
        stored = 0
        for start in range(0, len(rows), INSERT_CHUNK):
            statement = (
                pg_insert(TrafficTrace)
                .values(rows[start : start + INSERT_CHUNK])
                .on_conflict_do_nothing(index_elements=["project_id", "source", "external_id"])
                .returning(TrafficTrace.id)
            )
            stored += len((await self._session.execute(statement)).all())
        return stored

    def _filtered(self, query: Select[Any], project_id: uuid.UUID, where: TraceFilter, low: float, long_ms: int) -> Any:
        query = query.where(TrafficTrace.project_id == project_id)
        if where.source:
            query = query.where(TrafficTrace.source == where.source)
        if where.failed:
            query = query.where(TrafficTrace.status == "error")
        if where.low_rated:
            query = query.where(TrafficTrace.rating.is_not(None), TrafficTrace.rating <= low)
        if where.long:
            query = query.where(TrafficTrace.latency_ms.is_not(None), TrafficTrace.latency_ms >= long_ms)
        if where.unused:
            query = query.where(TrafficTrace.case_made_at.is_(None))
        if where.prompt_version:
            query = query.where(TrafficTrace.prompt_version == where.prompt_version)
        if where.since:
            query = query.where(TrafficTrace.started_at >= where.since)
        if where.until:
            query = query.where(TrafficTrace.started_at <= where.until)
        if where.q:
            escaped = where.q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            query = query.where(TrafficTrace.input_text.ilike(f"%{escaped}%", escape="\\"))
        if where.new_topic:
            earlier = aliased(TrafficTrace)
            seen_before = (
                select(1)
                .where(
                    earlier.project_id == TrafficTrace.project_id,
                    earlier.topic_hash == TrafficTrace.topic_hash,
                    earlier.started_at < TrafficTrace.started_at,
                )
                .exists()
            )
            query = query.where(not_(seen_before))
        return query

    async def page(
        self, project_id: uuid.UUID, where: TraceFilter, page: PageParams, low: float, long_ms: int
    ) -> list[TrafficTrace]:
        query = self._filtered(select(TrafficTrace), project_id, where, low, long_ms)
        if page.cursor is not None:
            query = query.where(TrafficTrace.id < page.cursor)
        query = query.order_by(TrafficTrace.id.desc()).limit(page.limit + 1)
        return list((await self._session.scalars(query)).all())

    async def select_for_cases(
        self, project_id: uuid.UUID, where: TraceFilter, limit: int, low: float, long_ms: int
    ) -> list[TrafficTrace]:
        query = self._filtered(select(TrafficTrace), project_id, where, low, long_ms)
        query = query.where(TrafficTrace.case_made_at.is_(None)).order_by(TrafficTrace.id.desc()).limit(limit)
        return list((await self._session.scalars(query)).all())

    async def traces(self, project_id: uuid.UUID, ids: Sequence[uuid.UUID]) -> list[TrafficTrace]:
        query = select(TrafficTrace).where(TrafficTrace.project_id == project_id, TrafficTrace.id.in_(list(ids)))
        return list((await self._session.scalars(query.order_by(TrafficTrace.id.desc()))).all())

    async def trace(self, project_id: uuid.UUID, trace_id: uuid.UUID) -> TrafficTrace | None:
        query = select(TrafficTrace).where(TrafficTrace.project_id == project_id, TrafficTrace.id == trace_id)
        return await self._session.scalar(query.execution_options(populate_existing=True))

    async def scores_of(self, trace_id: uuid.UUID) -> list[TrafficScore]:
        query = select(TrafficScore).where(TrafficScore.trace_id == trace_id).order_by(TrafficScore.id)
        return list((await self._session.scalars(query)).all())

    async def delete_trace(self, project_id: uuid.UUID, trace_id: uuid.UUID) -> int:
        result = await self._session.execute(
            delete(TrafficTrace).where(TrafficTrace.project_id == project_id, TrafficTrace.id == trace_id)
        )
        return int(result.rowcount or 0)  # type: ignore[attr-defined]

    async def mark_case_made(self, ids: Sequence[uuid.UUID], now: datetime) -> None:
        await self._session.execute(update(TrafficTrace).where(TrafficTrace.id.in_(list(ids))).values(case_made_at=now))

    async def purge(self, project_id: uuid.UUID, cutoff: datetime) -> int:
        """Deletes traces stored before the cutoff, a few thousand at a time so no lock is held for long."""
        total = 0
        while True:
            old = (
                select(TrafficTrace.id)
                .where(TrafficTrace.project_id == project_id, TrafficTrace.created_at < cutoff)
                .limit(PURGE_BATCH)
            )
            result = await self._session.execute(delete(TrafficTrace).where(TrafficTrace.id.in_(old)))
            deleted = int(result.rowcount or 0)  # type: ignore[attr-defined]
            total += deleted
            await self._session.flush()
            if deleted < PURGE_BATCH:
                break
        await self._session.execute(
            delete(TrafficIngestDay).where(
                TrafficIngestDay.project_id == project_id, TrafficIngestDay.day < cutoff.date() - timedelta(days=365)
            )
        )
        return total

    async def project_ids_with_traffic(self) -> list[uuid.UUID]:
        query = select(TrafficTrace.project_id).distinct()
        return list((await self._session.scalars(query)).all())

    # ------------------------------------------------------------------------------------------- ingest counters

    async def add_ingest_counts(self, project_id: uuid.UUID, day: date, **counts: int) -> None:
        values = {name: amount for name, amount in counts.items() if name in INGEST_COUNTERS and amount}
        if not values:
            return
        insert = pg_insert(TrafficIngestDay).values(project_id=project_id, day=day, **values)
        await self._session.execute(
            insert.on_conflict_do_update(
                index_elements=["project_id", "day"],
                set_={name: getattr(TrafficIngestDay, name) + insert.excluded[name] for name in values},
            )
        )

    async def ingest_days(self, project_id: uuid.UUID, since: date) -> list[TrafficIngestDay]:
        query = (
            select(TrafficIngestDay)
            .where(TrafficIngestDay.project_id == project_id, TrafficIngestDay.day >= since)
            .order_by(TrafficIngestDay.day)
        )
        return list((await self._session.scalars(query)).all())

    # ------------------------------------------------------------------------------------------- numbers

    async def counts(self, project_id: uuid.UUID) -> dict[str, Any]:
        base = select(func.count()).where(TrafficTrace.project_id == project_id)
        total = int(await self._session.scalar(base) or 0)
        by_source = (
            await self._session.execute(
                select(TrafficTrace.source, func.count())
                .where(TrafficTrace.project_id == project_id)
                .group_by(TrafficTrace.source)
            )
        ).all()
        by_state = (
            await self._session.execute(
                select(TrafficTrace.score_state, func.count())
                .where(TrafficTrace.project_id == project_id)
                .group_by(TrafficTrace.score_state)
            )
        ).all()
        span = (
            await self._session.execute(
                select(func.min(TrafficTrace.started_at), func.max(TrafficTrace.started_at)).where(
                    TrafficTrace.project_id == project_id
                )
            )
        ).one()
        return {
            "total": total,
            "by_source": {str(s): int(n) for s, n in by_source},
            "by_state": {str(s): int(n) for s, n in by_state},
            "oldest": span[0],
            "newest": span[1],
        }

    async def judged_since(self, project_id: uuid.UUID, since: datetime) -> int:
        query = select(func.count()).where(
            TrafficTrace.project_id == project_id, TrafficTrace.judged.is_(True), TrafficTrace.judged_at >= since
        )
        return int(await self._session.scalar(query) or 0)

    async def daily(self, project_id: uuid.UUID, since: datetime) -> list[Any]:
        day = func.date(func.timezone("UTC", TrafficTrace.started_at)).label("day")
        query = (
            select(
                day,
                TrafficTrace.prompt_version,
                func.count().label("traces"),
                func.count().filter(TrafficTrace.status == "error").label("errors"),
                func.count().filter(TrafficTrace.passed.is_not(None)).label("scored"),
                func.count().filter(TrafficTrace.passed.is_(True)).label("passed"),
                func.avg(TrafficTrace.quality).label("quality"),
                func.count().filter(TrafficTrace.judged.is_(True)).label("judged"),
            )
            .where(TrafficTrace.project_id == project_id, TrafficTrace.started_at >= since)
            .group_by(day, TrafficTrace.prompt_version)
            .order_by(day, TrafficTrace.prompt_version)
        )
        return list((await self._session.execute(query)).all())

    async def day_points(self, project_id: uuid.UUID, metric: str, since: datetime) -> list[tuple[date, int, int]]:
        """(day, good, total) for one metric: pass rate counts scored traces, success rate counts every trace."""
        day = func.date(func.timezone("UTC", TrafficTrace.started_at)).label("day")
        good: Any
        total: Any
        if metric == "pass_rate":
            good = func.count().filter(TrafficTrace.passed.is_(True))
            total = func.count().filter(TrafficTrace.passed.is_not(None))
        else:
            good = func.count().filter(TrafficTrace.status == "ok")
            total = func.count()
        query = (
            select(day, good, total)
            .where(TrafficTrace.project_id == project_id, TrafficTrace.started_at >= since)
            .group_by(day)
            .order_by(day)
        )
        return [(row[0], int(row[1]), int(row[2])) for row in (await self._session.execute(query)).all()]

    # ------------------------------------------------------------------------------------------- online scoring

    async def new_traces(self, project_id: uuid.UUID, limit: int) -> list[tuple[uuid.UUID, str]]:
        query = (
            select(TrafficTrace.id, TrafficTrace.source)
            .where(TrafficTrace.project_id == project_id, TrafficTrace.score_state == "new")
            .order_by(TrafficTrace.id)
            .limit(limit)
        )
        return [(row[0], str(row[1])) for row in (await self._session.execute(query)).all()]

    async def set_states(self, ids: Sequence[uuid.UUID], state: str, judge_sampled: bool = False) -> None:
        if ids:
            await self._session.execute(
                update(TrafficTrace)
                .where(TrafficTrace.id.in_(list(ids)))
                .values(score_state=state, judge_sampled=judge_sampled)
            )

    async def claim_queued(self, project_id: uuid.UUID, limit: int) -> list[TrafficTrace]:
        query = (
            select(TrafficTrace)
            .where(TrafficTrace.project_id == project_id, TrafficTrace.score_state == "queued")
            .order_by(TrafficTrace.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list((await self._session.scalars(query)).all())

    async def reset_states(self, project_id: uuid.UUID, states: Sequence[str]) -> None:
        """Puts traces back to "new" so a changed sample rate or a newly added check is applied to them."""
        await self._session.execute(
            update(TrafficTrace)
            .where(TrafficTrace.project_id == project_id, TrafficTrace.score_state.in_(list(states)))
            .values(score_state="new", judge_sampled=False)
        )

    async def save_scores(self, rows: list[dict[str, Any]]) -> None:
        if rows:
            await self._session.execute(pg_insert(TrafficScore).values(rows))

    async def finish_trace(self, trace_id: uuid.UUID, values: dict[str, Any]) -> None:
        await self._session.execute(update(TrafficTrace).where(TrafficTrace.id == trace_id).values(**values))

    # ------------------------------------------------------------------------------------------- alerts

    async def channels(self, project_id: uuid.UUID) -> list[AlertChannel]:
        query = select(AlertChannel).where(AlertChannel.project_id == project_id).order_by(AlertChannel.id)
        return list((await self._session.scalars(query)).all())

    async def channel(self, project_id: uuid.UUID, channel_id: uuid.UUID) -> AlertChannel | None:
        query = select(AlertChannel).where(AlertChannel.project_id == project_id, AlertChannel.id == channel_id)
        return await self._session.scalar(query.execution_options(populate_existing=True))

    async def channels_by_ids(self, project_id: uuid.UUID, ids: Sequence[uuid.UUID]) -> list[AlertChannel]:
        query = select(AlertChannel).where(AlertChannel.project_id == project_id, AlertChannel.id.in_(list(ids)))
        return list((await self._session.scalars(query)).all())

    async def delete_row(self, row: Any) -> None:
        await self._session.delete(row)
        await self._session.flush()

    async def rules(self, project_id: uuid.UUID, enabled_only: bool = False) -> list[AlertRule]:
        query = select(AlertRule).where(AlertRule.project_id == project_id)
        if enabled_only:
            query = query.where(AlertRule.enabled.is_(True))
        return list((await self._session.scalars(query.order_by(AlertRule.id))).all())

    async def rule(self, project_id: uuid.UUID, rule_id: uuid.UUID) -> AlertRule | None:
        query = select(AlertRule).where(AlertRule.project_id == project_id, AlertRule.id == rule_id)
        return await self._session.scalar(query.execution_options(populate_existing=True))

    async def open_alerts(self, project_id: uuid.UUID) -> list[Alert]:
        query = select(Alert).where(Alert.project_id == project_id, Alert.status == "open")
        return list((await self._session.scalars(query)).all())

    async def alerts(self, project_id: uuid.UUID, page: PageParams) -> list[tuple[Alert, str]]:
        query = (
            select(Alert, AlertRule.name)
            .join(AlertRule, AlertRule.id == Alert.rule_id)
            .where(Alert.project_id == project_id)
        )
        if page.cursor is not None:
            query = query.where(Alert.id < page.cursor)
        rows = (await self._session.execute(query.order_by(Alert.id.desc()).limit(page.limit + 1))).all()
        return [(row[0], str(row[1])) for row in rows]

    async def alert(self, project_id: uuid.UUID, alert_id: uuid.UUID) -> Alert | None:
        query = select(Alert).where(Alert.project_id == project_id, Alert.id == alert_id)
        return await self._session.scalar(query.execution_options(populate_existing=True))

    async def open_alert_ids(self, project_id: uuid.UUID) -> dict[uuid.UUID, uuid.UUID]:
        return {alert.rule_id: alert.id for alert in await self.open_alerts(project_id)}

    async def unnotified(self, project_id: uuid.UUID) -> list[Alert]:
        query = select(Alert).where(Alert.project_id == project_id, Alert.status == "open", Alert.notified_at.is_(None))
        return list((await self._session.scalars(query)).all())
