"""
Dataset use cases: the project's draft dataset version (created on first use) and, from
Step 4, reviewing, approving and splitting it.

A project keeps its test cases in one dataset; its newest version is the working draft
until it is approved. `ensure_draft` finds or creates that draft under the project's
advisory lock, so concurrent imports and generations share one draft. Other modules use
this service, never the dataset tables.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.datasets.models import Dataset, DatasetVersion
from app.modules.datasets.repository import DatasetRepository
from app.modules.datasets.schemas import DatasetVersionStatus


class DatasetService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._repo = DatasetRepository(session)
        self._settings = settings

    async def ensure_draft(self, project_id: uuid.UUID) -> DatasetVersion:
        await self._repo.lock_project(project_id)
        draft = await self._repo.draft_version(project_id)
        if draft is not None:
            return draft
        dataset = await self._repo.latest_dataset(project_id)
        if dataset is None:
            dataset = Dataset(project_id=project_id, name=self._settings.dataset_default_name)
            await self._repo.add(dataset)
        version = DatasetVersion(
            dataset_id=dataset.id,
            version=await self._repo.next_version_number(dataset.id),
            status=DatasetVersionStatus.DRAFT,
        )
        await self._repo.add(version)
        return version
