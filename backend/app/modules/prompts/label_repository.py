"""
Label data access.

Serving a prompt to an app is the hot path, so `served_version` resolves the prompt name, the
label and the version in one joined query. A label's history joins both versions and the
person's name in the same query; nothing is loaded per row.
"""

import uuid
from datetime import datetime

from sqlalchemy import column, delete, func, select, table
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.pagination import PageParams, keyset
from app.modules.prompts.models import Prompt, PromptLabel, PromptLabelMove, PromptVersion

USERS = table("users", column("id"), column("name"))


class LabelRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def labels(self, prompt_id: uuid.UUID) -> list[tuple[PromptLabel, int]]:
        query = (
            select(PromptLabel, PromptVersion.version)
            .join(PromptVersion, PromptVersion.id == PromptLabel.prompt_version_id)
            .where(PromptLabel.prompt_id == prompt_id)
            .order_by(PromptLabel.name)
        )
        return [(label, number) for label, number in (await self._session.execute(query)).all()]

    async def label(self, prompt_id: uuid.UUID, name: str, lock: bool = False) -> PromptLabel | None:
        query = select(PromptLabel).where(PromptLabel.prompt_id == prompt_id, PromptLabel.name == name)
        return await self._session.scalar(query.with_for_update() if lock else query)

    async def label_count(self, prompt_id: uuid.UUID) -> int:
        return int(await self._session.scalar(select(func.count()).where(PromptLabel.prompt_id == prompt_id)) or 0)

    async def add_label(self, row: PromptLabel) -> None:
        self._session.add(row)
        await self._session.flush()

    async def delete_label(self, label: PromptLabel) -> None:
        await self._session.execute(delete(PromptLabel).where(PromptLabel.id == label.id))

    async def add_move(self, move: PromptLabelMove) -> None:
        self._session.add(move)
        await self._session.flush()

    async def move_pairs(
        self, prompt_id: uuid.UUID, name: str, limit: int
    ) -> list[tuple[uuid.UUID | None, uuid.UUID | None]]:
        query = (
            select(PromptLabelMove.from_version_id, PromptLabelMove.to_version_id)
            .where(PromptLabelMove.prompt_id == prompt_id, PromptLabelMove.label == name)
            .order_by(PromptLabelMove.id.desc())
            .limit(limit)
        )
        return [(before, after) for before, after in (await self._session.execute(query)).all()]

    async def moves(
        self, prompt_id: uuid.UUID, name: str | None, page: PageParams
    ) -> list[tuple[PromptLabelMove, int | None, int | None, str | None]]:
        before, after = aliased(PromptVersion), aliased(PromptVersion)
        query = (
            select(PromptLabelMove, before.version, after.version, USERS.c.name)
            .outerjoin(before, before.id == PromptLabelMove.from_version_id)
            .outerjoin(after, after.id == PromptLabelMove.to_version_id)
            .outerjoin(USERS, USERS.c.id == PromptLabelMove.moved_by)
            .where(PromptLabelMove.prompt_id == prompt_id)
        )
        if name is not None:
            query = query.where(PromptLabelMove.label == name)
        query = keyset(query, PromptLabelMove.id, page)
        return [(move, a, b, who) for move, a, b, who in (await self._session.execute(query)).all()]

    async def served_version(
        self, project_id: uuid.UUID, name: str, label: str | None, version: int | None
    ) -> tuple[PromptVersion, datetime] | None:
        """The version an app should use: the one a label points at, a specific saved version, or the latest."""
        moment = PromptLabel.moved_at if label is not None else PromptVersion.created_at
        query = (
            select(PromptVersion, moment)
            .join(Prompt, Prompt.id == PromptVersion.prompt_id)
            .where(Prompt.project_id == project_id, Prompt.name == name, PromptVersion.is_candidate.is_(False))
        )
        if label is not None:
            query = query.join(
                PromptLabel,
                (PromptLabel.prompt_version_id == PromptVersion.id) & (PromptLabel.name == label),
            )
        elif version is not None:
            query = query.where(PromptVersion.version == version)
        query = query.order_by(Prompt.id, PromptVersion.version.desc()).limit(1)
        row = (await self._session.execute(query)).first()
        return None if row is None else (row[0], row[1])

    async def set_accept_label(self, prompt: Prompt, name: str | None) -> None:
        prompt.accept_moves_label = name
        await self._session.flush()
