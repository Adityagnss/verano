"""Activity read model: model calls grouped by local day, project, key, model and purpose."""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.gateway.models import LLMCall
from app.modules.gateway.schemas import CallStatus
from app.modules.projects.models import Project
from app.modules.registry.models import ProviderCredential


class ActivityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def projects(self, organization_ids: list[uuid.UUID]) -> list[tuple[uuid.UUID, str]]:
        rows = await self._session.execute(
            select(Project.id, Project.name).where(Project.organization_id.in_(organization_ids))
        )
        return [(row.id, row.name) for row in rows]

    async def credentials(self, project_ids: list[uuid.UUID]) -> list[Any]:
        result = await self._session.execute(
            select(
                ProviderCredential.id,
                ProviderCredential.project_id,
                ProviderCredential.provider,
                ProviderCredential.label,
                ProviderCredential.key_last4,
            ).where(ProviderCredential.project_id.in_(project_ids))
        )
        return list(result)

    async def daily(self, project_ids: list[uuid.UUID], tz: str, first: datetime, after: datetime) -> list[Any]:
        day = cast(func.timezone(tz, LLMCall.started_at), Date).label("day")
        reported = LLMCall.cached_input_tokens.is_not(None)
        result = await self._session.execute(
            select(
                day,
                LLMCall.project_id,
                LLMCall.credential_id,
                LLMCall.provider,
                LLMCall.model,
                LLMCall.purpose,
                func.count().label("requests"),
                func.count().filter(LLMCall.status == CallStatus.FAILED).label("failed"),
                func.coalesce(func.sum(LLMCall.input_tokens), 0).label("input_tokens"),
                func.coalesce(func.sum(LLMCall.output_tokens), 0).label("output_tokens"),
                func.coalesce(func.sum(LLMCall.cached_input_tokens), 0).label("cached_input_tokens"),
                func.coalesce(func.sum(LLMCall.reasoning_tokens), 0).label("reasoning_tokens"),
                func.coalesce(func.sum(case((reported, LLMCall.input_tokens), else_=0)), 0).label(
                    "input_tokens_with_cache_report"
                ),
                func.coalesce(func.sum(LLMCall.cost), 0).label("cost"),
                func.count()
                .filter(LLMCall.status == CallStatus.SUCCEEDED, LLMCall.cost.is_(None))
                .label("unknown_price_calls"),
            )
            .where(LLMCall.project_id.in_(project_ids), LLMCall.started_at >= first, LLMCall.started_at < after)
            .group_by(day, LLMCall.project_id, LLMCall.credential_id, LLMCall.provider, LLMCall.model, LLMCall.purpose)
        )
        return list(result)

    async def failures(self, project_ids: list[uuid.UUID], since: datetime, after: datetime) -> list[tuple[str, int]]:
        kind = func.coalesce(LLMCall.error_type, "unknown").label("kind")
        result = await self._session.execute(
            select(kind, func.count())
            .where(
                LLMCall.project_id.in_(project_ids),
                LLMCall.status == CallStatus.FAILED,
                LLMCall.started_at >= since,
                LLMCall.started_at < after,
            )
            .group_by(kind)
            .order_by(func.count().desc())
        )
        return [(str(kind), int(count)) for kind, count in result]


def as_date(value: date | datetime) -> date:
    return value.date() if isinstance(value, datetime) else value
