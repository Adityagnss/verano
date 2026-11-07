"""
Audit log HTTP routes (read-only): a filtered list, the actions that appear, and a download as CSV or JSON.

There is no route that changes or removes an entry. Who may read it (owners and admins) is decided by the
permission table, not here; the organization in the path is checked against the caller's membership first.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import Response

from app.core.pagination import Page, PageDep
from app.modules.audit.dependencies import AuditLogDep
from app.modules.audit.schemas import AuditActionOut, AuditEventOut, AuditExportQuery, AuditFilter

router = APIRouter(prefix="/organizations/{organization_id}/audit-log", tags=["audit"])


@router.get("")
async def list_events(
    organization_id: uuid.UUID, audit: AuditLogDep, page: PageDep, filters: Annotated[AuditFilter, Query()]
) -> Page[AuditEventOut]:
    return await audit.entries(organization_id, filters, page)


@router.get("/actions")
async def list_actions(organization_id: uuid.UUID, audit: AuditLogDep) -> list[AuditActionOut]:
    return await audit.actions(organization_id)


@router.get("/export")
async def export_events(
    organization_id: uuid.UUID,
    audit: AuditLogDep,
    query: Annotated[AuditExportQuery, Query()],
) -> Response:
    # one model for all query fields: FastAPI reads a model from the query string only when it is the only one
    body = await audit.export(organization_id, query, query.format == "csv")
    media = "text/csv" if query.format == "csv" else "application/json"
    headers = {"Content-Disposition": f'attachment; filename="audit-log.{query.format}"'}
    return Response(body, media_type=media, headers=headers)
