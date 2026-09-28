"""The project's LLM call history and its cost summary by purpose (read-only)."""

import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import Page, PageParams, to_page
from app.modules.gateway.repository import LLMCallRepository
from app.modules.gateway.schemas import CallPurpose, CostSummary, LLMCallOut, PurposeCost

ZERO = Decimal(0)


class CallHistoryService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = LLMCallRepository(session)

    async def calls(self, project_id: uuid.UUID, page: PageParams, purpose: CallPurpose | None) -> Page[LLMCallOut]:
        rows = await self._repo.page(project_id, page, purpose)
        return to_page([LLMCallOut.model_validate(row) for row in rows], page, lambda c: c.id)

    async def cost_summary(self, project_id: uuid.UUID) -> CostSummary:
        rows = await self._repo.cost_by_purpose(project_id)
        by_purpose = {
            purpose: PurposeCost(calls=calls, cost=cost, calls_with_unknown_price=unknown)
            for purpose, calls, cost, unknown in rows
        }
        return CostSummary(
            calls=sum(p.calls for p in by_purpose.values()),
            cost=sum((p.cost for p in by_purpose.values()), start=ZERO),
            calls_with_unknown_price=sum(p.calls_with_unknown_price for p in by_purpose.values()),
            by_purpose=by_purpose,
        )
