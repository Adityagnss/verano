"""
Registry data access: credentials and model profiles.

Profiles are written with one bulk `INSERT ... ON CONFLICT (credential_id, model_name)
DO UPDATE` per discovery, which refreshes metadata but keeps `is_selected`. Credential
listings include each credential's model count through one grouped subquery, not a query
per credential.
"""

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PageParams, keyset
from app.modules.registry.models import ModelProfile, ProviderCredential

UPSERT_REFRESHED = (
    "display_name",
    "litellm_model",
    "context_window",
    "max_output_tokens",
    "parameters",
    "supports_json_mode",
    "supports_system_prompt",
    "input_price_per_mtok",
    "output_price_per_mtok",
    "price_source",
    "discovered_at",
)


class RegistryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_credential(self, credential: ProviderCredential) -> ProviderCredential:
        self._session.add(credential)
        await self._session.flush()
        return credential

    async def credential(self, project_id: uuid.UUID, credential_id: uuid.UUID) -> ProviderCredential | None:
        query = select(ProviderCredential).where(
            ProviderCredential.id == credential_id, ProviderCredential.project_id == project_id
        )
        return await self._session.scalar(query)

    async def credentials_with_counts(self, project_id: uuid.UUID) -> list[tuple[ProviderCredential, int]]:
        counts = (
            select(ModelProfile.credential_id, func.count().label("n"))
            .where(ModelProfile.project_id == project_id)
            .group_by(ModelProfile.credential_id)
            .subquery()
        )
        query = (
            select(ProviderCredential, func.coalesce(counts.c.n, 0))
            .outerjoin(counts, counts.c.credential_id == ProviderCredential.id)
            .where(ProviderCredential.project_id == project_id)
            .order_by(ProviderCredential.id)
        )
        return [(row, int(n)) for row, n in (await self._session.execute(query)).all()]

    async def model_count(self, credential_id: uuid.UUID) -> int:
        query = select(func.count()).where(ModelProfile.credential_id == credential_id)
        return int(await self._session.scalar(query) or 0)

    async def update_credential(self, credential_id: uuid.UUID, values: dict[str, Any]) -> None:
        await self._session.execute(
            update(ProviderCredential).where(ProviderCredential.id == credential_id).values(**values)
        )

    async def delete_credential(self, credential_id: uuid.UUID) -> None:
        await self._session.execute(delete(ProviderCredential).where(ProviderCredential.id == credential_id))

    async def upsert_profiles(self, rows: Sequence[dict[str, Any]], discovered_at: datetime) -> None:
        if not rows:
            return
        statement = insert(ModelProfile).values([{**row, "discovered_at": discovered_at} for row in rows])
        statement = statement.on_conflict_do_update(
            index_elements=[ModelProfile.credential_id, ModelProfile.model_name],
            set_={name: statement.excluded[name] for name in UPSERT_REFRESHED},
        )
        await self._session.execute(statement)

    async def delete_profiles_not_in(self, credential_id: uuid.UUID, keep: Sequence[str]) -> None:
        await self._session.execute(
            delete(ModelProfile).where(
                ModelProfile.credential_id == credential_id, ModelProfile.model_name.not_in(keep)
            )
        )

    async def profiles(
        self, project_id: uuid.UUID, page: PageParams, selected_only: bool, credential_id: uuid.UUID | None
    ) -> list[ModelProfile]:
        query = select(ModelProfile).where(ModelProfile.project_id == project_id)
        if selected_only:
            query = query.where(ModelProfile.is_selected.is_(True))
        if credential_id is not None:
            query = query.where(ModelProfile.credential_id == credential_id)
        return list((await self._session.scalars(keyset(query, ModelProfile.id, page))).all())

    async def profiles_in(self, project_id: uuid.UUID, ids: Sequence[uuid.UUID] | None) -> list[ModelProfile]:
        query = select(ModelProfile).where(ModelProfile.project_id == project_id)
        query = query.where(ModelProfile.id.in_(ids)) if ids is not None else query.where(ModelProfile.is_selected)
        return list((await self._session.scalars(query.order_by(ModelProfile.id))).all())

    async def profile_by_name(self, credential_id: uuid.UUID, model_name: str) -> ModelProfile | None:
        query = select(ModelProfile).where(
            ModelProfile.credential_id == credential_id, ModelProfile.model_name == model_name
        )
        return await self._session.scalar(query)

    async def set_selected(self, project_id: uuid.UUID, profile_ids: Sequence[uuid.UUID], selected: bool) -> None:
        if not profile_ids:
            return
        await self._session.execute(
            update(ModelProfile)
            .where(ModelProfile.project_id == project_id, ModelProfile.id.in_(profile_ids))
            .values(is_selected=selected)
        )
