"""FastAPI wiring for the Activity page."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends

from app.core.database import SessionDep
from app.modules.activity.service import ActivityService
from app.modules.auth.dependencies import AuthServiceDep


def get_activity_service(session: SessionDep, auth: AuthServiceDep) -> ActivityService:
    return ActivityService(session, auth, lambda: datetime.now(UTC))


ActivityDep = Annotated[ActivityService, Depends(get_activity_service)]
