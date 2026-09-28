"""Task Spec data access: drafts and their confirmed form, always scoped to a project."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
