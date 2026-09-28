"""
Dataset data access: input files, the project's draft dataset version, and dataset items.

A project's test cases live in one dataset whose latest version is the working draft.
`lock_project` takes a transaction-scoped advisory lock per project, so two imports that
start at the same time can't both create a draft. Items are written in batches with one
multi-row INSERT each, and a file's items are replaced as a whole, which makes re-running an
import produce the same result instead of duplicates.
"""

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PageParams, keyset
from app.modules.datasets.models import Dataset, DatasetItem, DatasetVersion, InputFile
from app.modules.datasets.schemas import DatasetVersionStatus


class DatasetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, row: InputFile | Dataset | DatasetVersion) -> None:
        self._session.add(row)
        await self._session.flush()

    async def file(self, file_id: uuid.UUID, project_id: uuid.UUID | None = None) -> InputFile | None:
        query = select(InputFile).where(InputFile.id == file_id).execution_options(populate_existing=True)
        if project_id is not None:
            query = query.where(InputFile.project_id == project_id)
        return await self._session.scalar(query)

    async def files(self, project_id: uuid.UUID, page: PageParams) -> list[InputFile]:
        query = keyset(select(InputFile).where(InputFile.project_id == project_id), InputFile.id, page)
        return list((await self._session.scalars(query)).all())

    async def update_file(self, file_id: uuid.UUID, values: dict[str, Any]) -> None:
        await self._session.execute(update(InputFile).where(InputFile.id == file_id).values(**values))

    async def delete_file(self, file_id: uuid.UUID) -> None:
        await self._session.execute(delete(InputFile).where(InputFile.id == file_id))

    async def lock_project(self, project_id: uuid.UUID) -> None:
        await self._session.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(str(project_id), 0))))

    async def draft_version(self, project_id: uuid.UUID) -> DatasetVersion | None:
        query = (
            select(DatasetVersion)
            .join(Dataset, Dataset.id == DatasetVersion.dataset_id)
            .where(Dataset.project_id == project_id, DatasetVersion.status == DatasetVersionStatus.DRAFT)
            .order_by(DatasetVersion.version.desc())
            .limit(1)
        )
        return await self._session.scalar(query)

    async def latest_dataset(self, project_id: uuid.UUID) -> Dataset | None:
        query = select(Dataset).where(Dataset.project_id == project_id).order_by(Dataset.id.desc()).limit(1)
        return await self._session.scalar(query)

    async def next_version_number(self, dataset_id: uuid.UUID) -> int:
        current = await self._session.scalar(
            select(func.max(DatasetVersion.version)).where(DatasetVersion.dataset_id == dataset_id)
        )
        return int(current or 0) + 1

    async def next_position(self, version_id: uuid.UUID) -> int:
        current = await self._session.scalar(
            select(func.max(DatasetItem.position)).where(DatasetItem.dataset_version_id == version_id)
        )
        return 0 if current is None else int(current) + 1

    async def delete_file_items(self, version_id: uuid.UUID, file_id: uuid.UUID) -> None:
        await self._session.execute(
            delete(DatasetItem).where(
                DatasetItem.dataset_version_id == version_id, DatasetItem.input_file_id == file_id
            )
        )

    async def insert_items(self, rows: Sequence[dict[str, Any]]) -> None:
        if rows:
            await self._session.execute(insert(DatasetItem), list(rows))
