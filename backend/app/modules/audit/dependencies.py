"""FastAPI wiring for the audit log service."""

from typing import Annotated

from fastapi import Depends

from app.core.container import SettingsDep
from app.core.database import SessionDep
from app.modules.audit.service import AuditLog


def get_audit_log(session: SessionDep, settings: SettingsDep) -> AuditLog:
    return AuditLog(session, settings)


AuditLogDep = Annotated[AuditLog, Depends(get_audit_log)]
