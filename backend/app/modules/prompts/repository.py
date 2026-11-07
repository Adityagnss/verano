"""
Prompt data access.

A new version number is taken under a row lock on the prompt (`FOR UPDATE`), so two saves
racing on the same prompt get consecutive numbers instead of colliding. Listing prompts
loads every listed prompt's latest version in one `DISTINCT ON` query, not one per prompt.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PageParams, keyset
from app.modules.engine.models import Experiment
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

    async def next_version_number(self, prompt_id: uuid.UUID, candidate: bool = False) -> int:
        """Saved versions count 1, 2, 3...; Improve's candidates count -1, -2, -3... so testing them never
        uses up the numbers people see (an accepted candidate is saved again as the next real version)."""
        if candidate:
            lowest = await self._session.scalar(
                select(func.min(PromptVersion.version)).where(
                    PromptVersion.prompt_id == prompt_id, PromptVersion.version < 0
                )
            )
            return int(lowest or 0) - 1
        current = await self._session.scalar(
            select(func.max(PromptVersion.version)).where(
                PromptVersion.prompt_id == prompt_id, PromptVersion.version > 0
            )
        )
        return int(current or 0) + 1

    async def latest_versions(self, prompt_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, PromptVersion]:
        if not prompt_ids:
            return {}
        query = (
            select(PromptVersion)
            .where(PromptVersion.prompt_id.in_(prompt_ids), PromptVersion.is_candidate.is_(False))
            .ext(distinct_on(PromptVersion.prompt_id))
            .order_by(PromptVersion.prompt_id, PromptVersion.version.desc())
        )
        return {row.prompt_id: row for row in (await self._session.scalars(query)).all()}

    async def versions(self, prompt_id: uuid.UUID, page: PageParams) -> list[PromptVersion]:
        """The saved versions; Improve's candidates are not versions until accepted, so they are left out."""
        query = keyset(
            select(PromptVersion).where(PromptVersion.prompt_id == prompt_id, PromptVersion.is_candidate.is_(False)),
            PromptVersion.id,
            page,
        )
        return list((await self._session.scalars(query)).all())

    async def version(self, project_id: uuid.UUID, version_id: uuid.UUID) -> PromptVersion | None:
        query = (
            select(PromptVersion)
            .join(Prompt, Prompt.id == PromptVersion.prompt_id)
            .where(PromptVersion.id == version_id, Prompt.project_id == project_id)
        )
        return await self._session.scalar(query)

    async def version_of(self, prompt_id: uuid.UUID, version_id: uuid.UUID) -> PromptVersion | None:
        return await self._session.scalar(
            select(PromptVersion).where(PromptVersion.id == version_id, PromptVersion.prompt_id == prompt_id)
        )

    async def experiments_using(self, prompt_id: uuid.UUID) -> int:
        """How many experiments ran any version of this prompt (their results keep the version alive)."""
        versions = select(PromptVersion.id).where(PromptVersion.prompt_id == prompt_id)
        count = await self._session.scalar(
            select(func.count()).select_from(Experiment).where(Experiment.prompt_version_id.in_(versions))
        )
        return int(count or 0)

    async def delete_prompt(self, prompt_id: uuid.UUID) -> None:
        await self._session.execute(delete(Prompt).where(Prompt.id == prompt_id))
