"""
Audit data access: insert and filtered reads. There is deliberately no update or delete here.

Listings use keyset pagination on the time-ordered id, with one index per filter, so a page costs the same
however long the log is.
"""

import uuid
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PageParams, keyset
from app.modules.audit.models import AuditEvent
from app.modules.audit.schemas import AuditFilter
from app.modules.auth.models import User


class AuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, event: AuditEvent) -> None:
        self._session.add(event)
        await self._session.flush()

    async def actor_label(self, user_id: uuid.UUID) -> str | None:
        row = (await self._session.execute(select(User.name, User.email).where(User.id == user_id))).first()
        return None if row is None else f"{row.name} <{row.email}>"

    async def page(self, organization_id: uuid.UUID, filters: AuditFilter, page: PageParams) -> list[AuditEvent]:
        query = keyset(self._filtered(organization_id, filters), AuditEvent.id, page)
        return list((await self._session.scalars(query)).all())

    async def export(self, organization_id: uuid.UUID, filters: AuditFilter, limit: int) -> list[AuditEvent]:
        query = self._filtered(organization_id, filters).order_by(AuditEvent.id.desc()).limit(limit)
        return list((await self._session.scalars(query)).all())

    async def actions_seen(self, organization_id: uuid.UUID) -> list[str]:
        query = select(AuditEvent.action).where(AuditEvent.organization_id == organization_id).distinct()
        return list((await self._session.scalars(query)).all())

    @staticmethod
    def _filtered(organization_id: uuid.UUID, filters: AuditFilter) -> Select[Any]:
        query = select(AuditEvent).where(AuditEvent.organization_id == organization_id)
        if filters.actor_id is not None:
            query = query.where(AuditEvent.actor_id == filters.actor_id)
        if filters.action:
            query = query.where(AuditEvent.action == filters.action)
        if filters.project_id is not None:
            query = query.where(AuditEvent.project_id == filters.project_id)
        if filters.since is not None:
            query = query.where(AuditEvent.created_at >= filters.since)
        if filters.until is not None:
            query = query.where(AuditEvent.created_at < filters.until)
        return query
