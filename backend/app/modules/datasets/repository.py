"""
Dataset data access: input files, the project's draft dataset version, and dataset items.

A project's test cases live in one dataset whose latest version is the working draft.
`lock_project` takes a transaction-scoped advisory lock per project, so two imports that
start at the same time can't both create a draft. Items are written in batches with one
multi-row INSERT each, and a file's items are replaced as a whole, which makes re-running an
import produce the same result instead of duplicates. Item reads and writes for review
are always scoped to one dataset version, plus an optional filter or id list.
"""

import uuid
from collections.abc import Sequence
from typing import Any, TypeVar

from sqlalchemy import Delete, Select, Update, delete, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PageParams, keyset
from app.modules.datasets.models import Dataset, DatasetItem, DatasetVersion, InputFile
from app.modules.datasets.schemas import DatasetVersionStatus, ItemFilter, ItemSource, Split


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

    async def unpair_golden(self, version_id: uuid.UUID, golden_file_id: uuid.UUID, default_category: str) -> None:
        """Takes back the answers a golden-set file wrote onto input-file items."""
        paired = await self.items(version_id, ItemFilter(source=ItemSource.GOLDEN))
        for item in paired:
            if item.extra.get("golden_file_id") == str(golden_file_id):
                extra = {k: v for k, v in item.extra.items() if k not in ("golden_file_id", "golden_row")}
                values: dict[str, Any] = {
                    "expected_output": None,
                    "rubric": None,
                    "category": default_category,
                    "tags": [],
                    "source": ItemSource.INPUT_FILE,
                    "extra": extra,
                }
                await self.update_items(version_id, values, ids=[item.id])

    async def insert_items(self, rows: Sequence[dict[str, Any]]) -> None:
        if rows:
            await self._session.execute(insert(DatasetItem), list(rows))

    async def version(self, project_id: uuid.UUID, version_id: uuid.UUID, lock: bool = False) -> DatasetVersion | None:
        query = (
            select(DatasetVersion)
            .join(Dataset, Dataset.id == DatasetVersion.dataset_id)
            .where(DatasetVersion.id == version_id, Dataset.project_id == project_id)
            .execution_options(populate_existing=True)
        )
        return await self._session.scalar(query.with_for_update(of=DatasetVersion) if lock else query)

    async def latest_version(self, project_id: uuid.UUID) -> DatasetVersion | None:
        query = (
            select(DatasetVersion)
            .join(Dataset, Dataset.id == DatasetVersion.dataset_id)
            .where(Dataset.project_id == project_id)
            .order_by(DatasetVersion.id.desc())
            .limit(1)
        )
        return await self._session.scalar(query)

    async def update_version(self, version_id: uuid.UUID, values: dict[str, Any]) -> None:
        await self._session.execute(update(DatasetVersion).where(DatasetVersion.id == version_id).values(**values))

    async def items_page(self, version_id: uuid.UUID, where: ItemFilter, page: PageParams) -> list[DatasetItem]:
        query = _scoped(select(DatasetItem), version_id, where)
        if page.cursor is not None:
            query = query.where(DatasetItem.id > page.cursor)
        query = query.order_by(DatasetItem.id).limit(page.limit + 1)
        return list((await self._session.scalars(query)).all())

    async def items(
        self, version_id: uuid.UUID, where: ItemFilter | None = None, ids: Sequence[uuid.UUID] | None = None
    ) -> list[DatasetItem]:
        query = _scoped(select(DatasetItem), version_id, where, ids).order_by(DatasetItem.position)
        return list((await self._session.scalars(query.execution_options(populate_existing=True))).all())

    async def item(self, version_id: uuid.UUID, item_id: uuid.UUID) -> DatasetItem | None:
        query = _scoped(select(DatasetItem), version_id, None, [item_id])
        item: DatasetItem | None = await self._session.scalar(query.execution_options(populate_existing=True))
        return item

    async def update_items(
        self,
        version_id: uuid.UUID,
        values: dict[str, Any],
        where: ItemFilter | None = None,
        ids: Sequence[uuid.UUID] | None = None,
    ) -> None:
        await self._session.execute(_scoped(update(DatasetItem), version_id, where, ids).values(**values))

    async def delete_items(
        self, version_id: uuid.UUID, where: ItemFilter | None = None, ids: Sequence[uuid.UUID] | None = None
    ) -> None:
        await self._session.execute(_scoped(delete(DatasetItem), version_id, where, ids))

    async def set_splits(self, splits: dict[uuid.UUID, Split]) -> None:
        for split in Split:
            ids = [item_id for item_id, value in splits.items() if value is split]
            if ids:
                await self._session.execute(update(DatasetItem).where(DatasetItem.id.in_(ids)).values(split=split))


Q = TypeVar("Q", Select[Any], Update, Delete)


def _scoped(query: Q, version_id: uuid.UUID, where: ItemFilter | None, ids: Sequence[uuid.UUID] | None = None) -> Q:
    query = query.where(DatasetItem.dataset_version_id == version_id)
    for name, value in (where.model_dump(exclude_none=True) if where else {}).items():
        query = query.where(getattr(DatasetItem, name) == value)
    if ids is not None:
        query = query.where(DatasetItem.id.in_(ids))
    return query
