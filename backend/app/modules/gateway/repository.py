"""
Gateway data access: writing call records and reading them back for cost tracking.

The gateway records each call in its own short transaction (see service), so a call's
record survives even if the caller's transaction later rolls back: money spent is always
visible. The cost summary is one grouped SQL aggregate, not a Python loop.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PageParams, keyset
from app.modules.gateway.models import LLMCall
from app.modules.gateway.schemas import CallPurpose


class LLMCallRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, values: dict[str, Any]) -> uuid.UUID:
        call = LLMCall(**values)
        self._session.add(call)
        await self._session.flush()
        return call.id

    async def page(self, project_id: uuid.UUID, page: PageParams, purpose: CallPurpose | None) -> list[LLMCall]:
        query = select(LLMCall).where(LLMCall.project_id == project_id)
        if purpose is not None:
            query = query.where(LLMCall.purpose == purpose)
        return list((await self._session.scalars(keyset(query, LLMCall.id, page))).all())

    async def spent_since(self, project_ids: list[uuid.UUID], since: datetime) -> Decimal:
        """Money spent by these projects' calls since a moment (unknown prices count as nothing)."""
        if not project_ids:
            return Decimal(0)
        query = select(func.coalesce(func.sum(LLMCall.cost), 0)).where(
            LLMCall.project_id.in_(project_ids), LLMCall.started_at >= since
        )
        return Decimal(await self._session.scalar(query) or 0)

    async def cost_by_purpose(self, project_id: uuid.UUID) -> list[tuple[CallPurpose, int, Any, int]]:
        unknown = func.sum(case((LLMCall.cost.is_(None) & (LLMCall.status == "succeeded"), 1), else_=0))
        query = (
            select(LLMCall.purpose, func.count(), func.coalesce(func.sum(LLMCall.cost), 0), unknown)
            .where(LLMCall.project_id == project_id)
            .group_by(LLMCall.purpose)
        )
        return [
            (purpose, int(n), cost, int(u or 0)) for purpose, n, cost, u in (await self._session.execute(query)).all()
        ]
