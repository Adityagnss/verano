"""Document sections data access: replace a file's sections in one go, and read them back."""

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PageParams
from app.modules.documents.models import DocumentSection


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def replace_sections(self, file_id: uuid.UUID, rows: Sequence[dict[str, Any]]) -> None:
        await self._session.execute(delete(DocumentSection).where(DocumentSection.input_file_id == file_id))
        if rows:
            await self._session.execute(insert(DocumentSection), list(rows))

    async def sections(self, file_id: uuid.UUID, page: PageParams) -> list[DocumentSection]:
        query = select(DocumentSection).where(DocumentSection.input_file_id == file_id)
        if page.cursor is not None:
            query = query.where(DocumentSection.id > page.cursor)
        query = query.order_by(DocumentSection.id).limit(page.limit + 1)
        return list((await self._session.scalars(query)).all())
