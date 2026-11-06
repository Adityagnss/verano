"""
The workspace monthly spending limit, checked before every gateway call and between batches of a run (ADR 0030).

`reason` answers "has this project's workspace reached its limit this month?" with a plain sentence or None.
It opens its own short session, so it never holds the caller's transaction. With no limit set it costs one
joined query; the month's total is only summed when a limit exists. `check` raises `SpendLimitReached`, which a
run records as the reason its calls were not made.
"""

import uuid
from collections.abc import Callable
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import AppError
from app.core.security import utcnow
from app.modules.gateway.repository import LLMCallRepository
from app.modules.organizations.domain import limit_reached, month_start, reached_message
from app.modules.organizations.repository import OrganizationRepository
from app.modules.projects.repository import ProjectRepository


class SpendLimitReached(AppError):
    status_code = 402
    code = "spend_limit_reached"


class SpendGuard:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], clock: Callable[[], datetime] = utcnow) -> None:
        self._sessions = sessions
        self._clock = clock

    async def reason(self, project_id: uuid.UUID) -> str | None:
        now = self._clock()
        async with self._sessions() as session:
            found = await OrganizationRepository(session).limit_for_project(project_id)
            if found is None:
                return None
            organization_id, limit = found
            if limit is None:
                return None
            project_ids = await ProjectRepository(session).ids_in_organization(organization_id)
            spent = await LLMCallRepository(session).spent_since(project_ids, month_start(now))
        return reached_message(spent, limit, now) if limit_reached(spent, limit) else None

    async def check(self, project_id: uuid.UUID) -> None:
        why = await self.reason(project_id)
        if why:
            raise SpendLimitReached(why)
