"""Task Spec data access: drafts and their confirmed form, always scoped to a project."""

import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.gateway.models import LLMCall
from app.modules.gateway.schemas import CallPurpose
from app.modules.generator.models import TaskSpecRecord


class TaskSpecRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, row: TaskSpecRecord) -> None:
        self._session.add(row)
        await self._session.flush()

    async def get(self, project_id: uuid.UUID, spec_id: uuid.UUID) -> TaskSpecRecord | None:
        query = select(TaskSpecRecord).where(TaskSpecRecord.id == spec_id, TaskSpecRecord.project_id == project_id)
        return await self._session.scalar(query.execution_options(populate_existing=True))

    async def run_spend(self, project_id: uuid.UUID, run_id: str) -> Decimal:
        """What the model calls of one generation run have cost so far (calls carry a `run` label)."""
        total = await self._session.scalar(
            select(func.coalesce(func.sum(LLMCall.cost), 0)).where(
                LLMCall.project_id == project_id,
                LLMCall.purpose == CallPurpose.GENERATION,
                LLMCall.labels["run"].as_string() == run_id,
            )
        )
        return Decimal(total or 0)
