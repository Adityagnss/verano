"""Apps data access: targets, their credential and profile, and the recorded calls."""

import uuid
from typing import Any, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.apps.models import AppCall, AppTarget
from app.modules.registry.models import ModelProfile, ProviderCredential

Row = TypeVar("Row")


class AppRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, row: Row) -> Row:
        self._session.add(row)
        await self._session.flush()
        return row

    async def delete(self, row: Any) -> None:
        await self._session.delete(row)
        await self._session.flush()

    async def targets(self, project_id: uuid.UUID) -> list[AppTarget]:
        query = select(AppTarget).where(AppTarget.project_id == project_id).order_by(AppTarget.id)
        return list((await self._session.scalars(query)).all())

    async def target(self, project_id: uuid.UUID, target_id: uuid.UUID) -> AppTarget | None:
        query = select(AppTarget).where(AppTarget.project_id == project_id, AppTarget.id == target_id)
        return await self._session.scalar(query)

    async def target_by_profile(self, model_profile_id: uuid.UUID) -> AppTarget | None:
        return await self._session.scalar(select(AppTarget).where(AppTarget.model_profile_id == model_profile_id))

    async def target_by_credential(self, credential_id: uuid.UUID) -> AppTarget | None:
        return await self._session.scalar(select(AppTarget).where(AppTarget.credential_id == credential_id))

    async def credential(self, credential_id: uuid.UUID) -> ProviderCredential | None:
        return await self._session.get(ProviderCredential, credential_id)

    async def profile(self, profile_id: uuid.UUID) -> ModelProfile | None:
        return await self._session.get(ModelProfile, profile_id)

    async def add_calls(self, rows: list[AppCall]) -> None:
        self._session.add_all(rows)
        await self._session.flush()

    async def calls(self, experiment_id: uuid.UUID, test_case_run_id: uuid.UUID) -> list[AppCall]:
        query = (
            select(AppCall)
            .where(AppCall.experiment_id == experiment_id, AppCall.test_case_run_id == test_case_run_id)
            .order_by(AppCall.turn, AppCall.id)
        )
        return list((await self._session.scalars(query)).all())

    async def calls_in_project(
        self, project_id: uuid.UUID, experiment_id: uuid.UUID, test_case_run_id: uuid.UUID
    ) -> list[AppCall]:
        """The recorded calls of one case, only for apps that belong to this project."""
        query = (
            select(AppCall)
            .join(AppTarget, AppTarget.id == AppCall.app_target_id)
            .where(
                AppTarget.project_id == project_id,
                AppCall.experiment_id == experiment_id,
                AppCall.test_case_run_id == test_case_run_id,
            )
            .order_by(AppCall.turn, AppCall.id)
        )
        return list((await self._session.scalars(query)).all())
