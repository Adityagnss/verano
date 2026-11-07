"""
Audit log shapes: the actions that are recorded, one entry as the API shows it, and the filter.

Entries are append-only: there is no route and no service method that changes or deletes one (ADR 0034).
"""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AuditAction(StrEnum):
    KEY_ADDED = "key.added"
    KEY_ROTATED = "key.rotated"
    KEY_REMOVED = "key.removed"
    KEY_ATTACHED = "key.attached"
    KEY_DETACHED = "key.detached"
    VERSION_ACCEPTED = "version.accepted"
    LABEL_MOVED = "label.moved"
    ANSWER_LABELLED = "answer.labelled"
    ROLE_CHANGED = "role.changed"
    MEMBER_REMOVED = "member.removed"
    MEMBER_JOINED = "member.joined"
    INVITE_SENT = "invite.sent"
    INVITE_REVOKED = "invite.revoked"
    INVITE_ACCEPTED = "invite.accepted"
    LIMIT_CHANGED = "limit.changed"
    TOKEN_CREATED = "token.created"
    TOKEN_REVOKED = "token.revoked"


ACTION_LABELS: dict[AuditAction, str] = {
    AuditAction.KEY_ADDED: "Key added",
    AuditAction.KEY_ROTATED: "Key rotated",
    AuditAction.KEY_REMOVED: "Key removed",
    AuditAction.KEY_ATTACHED: "Key used in a project",
    AuditAction.KEY_DETACHED: "Key taken out of a project",
    AuditAction.VERSION_ACCEPTED: "Prompt version accepted",
    AuditAction.LABEL_MOVED: "Prompt label moved",
    AuditAction.ANSWER_LABELLED: "Answer labelled",
    AuditAction.ROLE_CHANGED: "Role changed",
    AuditAction.MEMBER_REMOVED: "Member removed",
    AuditAction.MEMBER_JOINED: "Member joined",
    AuditAction.INVITE_SENT: "Invite sent",
    AuditAction.INVITE_REVOKED: "Invite withdrawn",
    AuditAction.INVITE_ACCEPTED: "Invite accepted",
    AuditAction.LIMIT_CHANGED: "Spending limit changed",
    AuditAction.TOKEN_CREATED: "API token created",
    AuditAction.TOKEN_REVOKED: "API token revoked",
}


class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    action: str
    action_label: str
    actor_id: uuid.UUID | None
    actor_name: str | None
    project_id: uuid.UUID | None
    target_type: str | None
    target_id: str | None
    summary: str
    details: dict[str, Any]


class AuditActionOut(BaseModel):
    action: str
    label: str


class AuditFilter(BaseModel):
    actor_id: uuid.UUID | None = None
    action: str | None = Field(default=None, max_length=64)
    project_id: uuid.UUID | None = None
    since: datetime | None = None
    until: datetime | None = None


class AuditExportQuery(AuditFilter):
    format: Literal["csv", "json"] = "csv"
