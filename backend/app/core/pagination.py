"""
Keyset (cursor) pagination.

Every list endpoint returns `Page[T]`: `items` plus an opaque `next_cursor`. The cursor
encodes the last row's UUIDv7 id; because ids are time-ordered, "rows after this id" is an
index range scan whose cost does not grow with the page number, unlike OFFSET.
Repositories apply `keyset()` to their query; routers accept `PageParams`.
"""

import base64
import uuid
from collections.abc import Callable, Sequence
from typing import Annotated, Any, Generic, TypeVar

from fastapi import Depends, Query
from pydantic import BaseModel
from sqlalchemy import Select
from sqlalchemy.orm import InstrumentedAttribute

from app.core.container import SettingsDep
from app.core.errors import ValidationFailed

T = TypeVar("T")
S = TypeVar("S", bound=Select[Any])


class Page(BaseModel, Generic[T]):
    items: list[T]
    next_cursor: str | None


class PageParams(BaseModel):
    limit: int
    cursor: uuid.UUID | None


def encode_cursor(last_id: uuid.UUID) -> str:
    return base64.urlsafe_b64encode(last_id.bytes).decode().rstrip("=")


def decode_cursor(cursor: str) -> uuid.UUID:
    try:
        return uuid.UUID(bytes=base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
    except ValueError as exc:
        raise ValidationFailed("The pagination cursor is not valid.") from exc


def page_params(
    settings: SettingsDep,
    limit: Annotated[int | None, Query(ge=1)] = None,
    cursor: Annotated[str | None, Query()] = None,
) -> PageParams:
    size = min(limit or settings.pagination_default_limit, settings.pagination_max_limit)
    return PageParams(limit=size, cursor=decode_cursor(cursor) if cursor else None)


PageDep = Annotated[PageParams, Depends(page_params)]


def keyset(query: S, id_column: InstrumentedAttribute[uuid.UUID], params: PageParams) -> S:
    if params.cursor is not None:
        query = query.where(id_column < params.cursor)
    return query.order_by(id_column.desc()).limit(params.limit + 1)


def to_page(rows: Sequence[T], params: PageParams, id_of: Callable[[T], uuid.UUID]) -> Page[T]:
    has_more = len(rows) > params.limit
    items = list(rows[: params.limit])
    next_cursor = encode_cursor(id_of(items[-1])) if has_more and items else None
    return Page[T](items=items, next_cursor=next_cursor)
