"""Security data access: packs, their cases, and the earlier runs of a pack's dataset (for the drop check)."""

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.engine.models import Experiment
from app.modules.engine.schemas import ExperimentStatus
from app.modules.security.models import SecurityCase, SecurityPack


class SecurityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_pack(self, pack: SecurityPack) -> None:
        self._session.add(pack)
        await self._session.flush()

    async def pack(self, pack_id: uuid.UUID, project_id: uuid.UUID | None = None) -> SecurityPack | None:
        query = select(SecurityPack).where(SecurityPack.id == pack_id)
        if project_id is not None:
            query = query.where(SecurityPack.project_id == project_id)
        return await self._session.scalar(query.execution_options(populate_existing=True))

    async def packs(self, project_id: uuid.UUID, limit: int) -> list[SecurityPack]:
        query = (
            select(SecurityPack)
            .where(SecurityPack.project_id == project_id)
            .order_by(SecurityPack.id.desc())
            .limit(limit)
        )
        return list((await self._session.scalars(query)).all())

    async def update_pack(self, pack_id: uuid.UUID, values: dict[str, Any], status_was: str | None = None) -> bool:
        query = update(SecurityPack).where(SecurityPack.id == pack_id)
        if status_was is not None:
            query = query.where(SecurityPack.status == status_was)
        result = await self._session.execute(query.values(**values))
        return bool(getattr(result, "rowcount", 0))

    async def delete_pack(self, pack_id: uuid.UUID) -> None:
        await self._session.execute(delete(SecurityPack).where(SecurityPack.id == pack_id))

    async def insert_cases(self, rows: Sequence[dict[str, Any]]) -> None:
        if rows:
            await self._session.execute(insert(SecurityCase).values(list(rows)))

    async def delete_cases(self, pack_id: uuid.UUID) -> None:
        await self._session.execute(delete(SecurityCase).where(SecurityCase.pack_id == pack_id))

    async def cases(self, pack_id: uuid.UUID, status: str | None = None) -> list[SecurityCase]:
        query = select(SecurityCase).where(SecurityCase.pack_id == pack_id)
        if status is not None:
            query = query.where(SecurityCase.status == status)
        return list(
            (
                await self._session.scalars(
                    query.order_by(SecurityCase.category, SecurityCase.position).execution_options(
                        populate_existing=True
                    )
                )
            ).all()
        )

    async def case(self, pack_id: uuid.UUID, case_id: uuid.UUID) -> SecurityCase | None:
        query = select(SecurityCase).where(SecurityCase.pack_id == pack_id, SecurityCase.id == case_id)
        return await self._session.scalar(query.execution_options(populate_existing=True))

    async def update_cases(
        self,
        pack_id: uuid.UUID,
        values: dict[str, Any],
        category: str | None = None,
        ids: list[uuid.UUID] | None = None,
    ) -> None:
        query = update(SecurityCase).where(SecurityCase.pack_id == pack_id)
        if category is not None:
            query = query.where(SecurityCase.category == category)
        if ids is not None:
            query = query.where(SecurityCase.id.in_(ids))
        await self._session.execute(query.values(**values))

    async def counts(self, pack_id: uuid.UUID) -> list[tuple[str, str, int]]:
        rows = await self._session.execute(
            select(SecurityCase.category, SecurityCase.status, func.count())
            .where(SecurityCase.pack_id == pack_id)
            .group_by(SecurityCase.category, SecurityCase.status)
        )
        return [(row[0], row[1], int(row[2])) for row in rows.all()]

    async def earlier_completed(self, dataset_version_id: uuid.UUID, before: uuid.UUID) -> Experiment | None:
        """The newest finished run on this dataset version that started before `before`."""
        query = (
            select(Experiment)
            .where(
                Experiment.dataset_version_id == dataset_version_id,
                Experiment.status == ExperimentStatus.COMPLETED,
                Experiment.id < before,
            )
            .order_by(Experiment.id.desc())
            .limit(1)
        )
        return await self._session.scalar(query)

    async def pack_for_dataset(self, dataset_version_id: uuid.UUID) -> SecurityPack | None:
        return await self._session.scalar(
            select(SecurityPack).where(SecurityPack.dataset_version_id == dataset_version_id)
        )
