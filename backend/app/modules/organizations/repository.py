"""
Organization data access: shared keys and workspace settings.

`limit_for_project` is one joined query (project to its workspace's settings), because the gateway asks it before
every call; the spend total is only computed when a limit is set.
"""

import uuid
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.models import OrganizationKey, OrganizationSettings
from app.modules.projects.models import Project


class OrganizationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_key(self, key: OrganizationKey) -> OrganizationKey:
        self._session.add(key)
        await self._session.flush()
        return key

    async def keys(self, organization_id: uuid.UUID) -> list[OrganizationKey]:
        query = select(OrganizationKey).where(OrganizationKey.organization_id == organization_id)
        return list((await self._session.scalars(query.order_by(OrganizationKey.id))).all())

    async def key(
        self, organization_id: uuid.UUID, key_id: uuid.UUID, for_update: bool = False
    ) -> OrganizationKey | None:
        query = select(OrganizationKey).where(
            OrganizationKey.id == key_id, OrganizationKey.organization_id == organization_id
        )
        return await self._session.scalar(query.with_for_update() if for_update else query)

    async def delete_key(self, key_id: uuid.UUID) -> None:
        await self._session.execute(delete(OrganizationKey).where(OrganizationKey.id == key_id))

    async def limit(self, organization_id: uuid.UUID) -> Decimal | None:
        query = select(OrganizationSettings.monthly_spend_limit).where(
            OrganizationSettings.organization_id == organization_id
        )
        return await self._session.scalar(query)

    async def limit_for_project(self, project_id: uuid.UUID) -> tuple[uuid.UUID, Decimal | None] | None:
        query = (
            select(Project.organization_id, OrganizationSettings.monthly_spend_limit)
            .outerjoin(OrganizationSettings, OrganizationSettings.organization_id == Project.organization_id)
            .where(Project.id == project_id)
        )
        row = (await self._session.execute(query)).first()
        return None if row is None else (row[0], row[1])

    async def set_limit(self, organization_id: uuid.UUID, limit: Decimal | None, user_id: uuid.UUID) -> None:
        statement = insert(OrganizationSettings).values(
            organization_id=organization_id, monthly_spend_limit=limit, updated_by=user_id
        )
        await self._session.execute(
            statement.on_conflict_do_update(
                index_elements=[OrganizationSettings.organization_id],
                set_={"monthly_spend_limit": limit, "updated_by": user_id},
            )
        )
