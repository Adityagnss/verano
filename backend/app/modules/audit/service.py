"""
The audit log service: `AuditLog.record(...)` for other modules, and listing and export for the screen.

`record` writes one row in the caller's own session, so the entry is committed together with the change it
describes (if the change rolls back, so does its entry). It never raises for a missing actor: system changes
are recorded without one. The listing is for owners and admins (enforced by the permission table).
"""

import json
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.pagination import Page, PageParams, to_page
from app.modules.audit.domain import clean_details, to_csv
from app.modules.audit.models import AuditEvent
from app.modules.audit.repository import AuditRepository
from app.modules.audit.schemas import ACTION_LABELS, AuditAction, AuditActionOut, AuditEventOut, AuditFilter


def event_out(row: AuditEvent) -> AuditEventOut:
    try:
        label = ACTION_LABELS[AuditAction(row.action)]
    except ValueError:
        label = row.action
    return AuditEventOut(
        id=row.id,
        created_at=row.created_at,
        action=row.action,
        action_label=label,
        actor_id=row.actor_id,
        actor_name=row.actor_name,
        project_id=row.project_id,
        target_type=row.target_type,
        target_id=row.target_id,
        summary=row.summary,
        details=row.details,
    )


class AuditLog:
    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self._repo = AuditRepository(session)
        self._settings = settings

    async def record(
        self,
        *,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID | None,
        action: AuditAction,
        summary: str,
        target_type: str | None = None,
        target_id: uuid.UUID | str | None = None,
        project_id: uuid.UUID | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Add one entry: who (`actor_id`), what (`action`, `summary`), on what (`target_*`) and anything useful in
        `details` (never a secret; secret-looking fields are hidden)."""
        await self._repo.add(
            AuditEvent(
                organization_id=organization_id,
                project_id=project_id,
                actor_id=actor_id,
                actor_name=await self._repo.actor_label(actor_id) if actor_id else None,
                action=action.value,
                target_type=target_type,
                target_id=str(target_id) if target_id is not None else None,
                summary=summary[:2000],
                details=clean_details(details),
            )
        )

    async def entries(self, organization_id: uuid.UUID, filters: AuditFilter, page: PageParams) -> Page[AuditEventOut]:
        rows = await self._repo.page(organization_id, filters, page)
        return to_page([event_out(row) for row in rows], page, lambda event: event.id)

    async def actions(self, organization_id: uuid.UUID) -> list[AuditActionOut]:
        seen = set(await self._repo.actions_seen(organization_id))
        return [AuditActionOut(action=a.value, label=ACTION_LABELS[a]) for a in AuditAction if a.value in seen]

    async def export(self, organization_id: uuid.UUID, filters: AuditFilter, as_csv: bool) -> str:
        limit = self._settings.audit_export_max_rows if self._settings else 100_000
        events = [event_out(row) for row in await self._repo.export(organization_id, filters, limit)]
        if as_csv:
            return to_csv(events)
        return json.dumps([event.model_dump(mode="json") for event in events], indent=2)
