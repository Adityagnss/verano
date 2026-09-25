"""Project data access, with keyset pagination over the caller's organizations."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PageParams, keyset
from app.modules.projects.models import Project


class ProjectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, project: Project) -> Project:
        self._session.add(project)
        await self._session.flush()
        return project

    async def get_in(self, project_id: uuid.UUID, organization_ids: list[uuid.UUID]) -> Project | None:
        query = select(Project).where(Project.id == project_id, Project.organization_id.in_(organization_ids))
        return await self._session.scalar(query)

    async def list_in(self, organization_ids: list[uuid.UUID], page: PageParams) -> list[Project]:
        query = keyset(select(Project).where(Project.organization_id.in_(organization_ids)), Project.id, page)
        return list((await self._session.scalars(query)).all())
