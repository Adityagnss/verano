"""Project data access, with keyset pagination over the caller's organizations."""

import uuid

from sqlalchemy import delete, func, select
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

    async def organization_id_of(self, project_id: uuid.UUID) -> uuid.UUID | None:
        return await self._session.scalar(select(Project.organization_id).where(Project.id == project_id))

    async def ids_in_organization(self, organization_id: uuid.UUID) -> list[uuid.UUID]:
        query = select(Project.id).where(Project.organization_id == organization_id)
        return list((await self._session.scalars(query)).all())

    async def list_in(self, organization_ids: list[uuid.UUID], page: PageParams) -> list[Project]:
        query = keyset(select(Project).where(Project.organization_id.in_(organization_ids)), Project.id, page)
        return list((await self._session.scalars(query)).all())

    async def name_taken(self, organization_id: uuid.UUID, name: str, except_id: uuid.UUID | None = None) -> bool:
        """Is there already a project of this name in the workspace? Case and surrounding spaces don't count."""
        query = select(Project.id).where(
            Project.organization_id == organization_id,
            func.lower(func.trim(Project.name)) == name.strip().lower(),
        )
        if except_id is not None:
            query = query.where(Project.id != except_id)
        return await self._session.scalar(query.limit(1)) is not None

    async def rename(self, project_id: uuid.UUID, name: str) -> Project | None:
        project = await self._session.get(Project, project_id)
        if project is not None:
            project.name = name
            await self._session.flush()
        return project

    async def remove(self, project_id: uuid.UUID) -> None:
        await self._session.execute(delete(Project).where(Project.id == project_id))
