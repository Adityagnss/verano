"""
Prompt data access.

A new version number is taken under a row lock on the prompt (`FOR UPDATE`), so two saves
racing on the same prompt get consecutive numbers instead of colliding. Listing prompts
loads every listed prompt's latest version in one `DISTINCT ON` query, not one per prompt.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PageParams, keyset
from app.modules.prompts.models import Prompt, PromptVersion


class PromptRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, row: Prompt | PromptVersion) -> None:
        self._session.add(row)
        await self._session.flush()

    async def prompt(self, project_id: uuid.UUID, prompt_id: uuid.UUID, lock: bool = False) -> Prompt | None:
        query = select(Prompt).where(Prompt.id == prompt_id, Prompt.project_id == project_id)
        return await self._session.scalar(query.with_for_update() if lock else query)

    async def prompts(self, project_id: uuid.UUID, page: PageParams) -> list[Prompt]:
        query = keyset(select(Prompt).where(Prompt.project_id == project_id), Prompt.id, page)
        return list((await self._session.scalars(query)).all())

    async def next_version_number(self, prompt_id: uuid.UUID) -> int:
        current = await self._session.scalar(
            select(func.max(PromptVersion.version)).where(PromptVersion.prompt_id == prompt_id)
        )
        return int(current or 0) + 1

    async def latest_versions(self, prompt_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, PromptVersion]:
        if not prompt_ids:
            return {}
        query = (
            select(PromptVersion)
            .where(PromptVersion.prompt_id.in_(prompt_ids))
            .ext(distinct_on(PromptVersion.prompt_id))
            .order_by(PromptVersion.prompt_id, PromptVersion.version.desc())
        )
        return {row.prompt_id: row for row in (await self._session.scalars(query)).all()}

    async def versions(self, prompt_id: uuid.UUID, page: PageParams) -> list[PromptVersion]:
        query = keyset(select(PromptVersion).where(PromptVersion.prompt_id == prompt_id), PromptVersion.id, page)
        return list((await self._session.scalars(query)).all())

    async def version(self, project_id: uuid.UUID, version_id: uuid.UUID) -> PromptVersion | None:
        query = (
            select(PromptVersion)
            .join(Prompt, Prompt.id == PromptVersion.prompt_id)
            .where(PromptVersion.id == version_id, Prompt.project_id == project_id)
        )
        return await self._session.scalar(query)
