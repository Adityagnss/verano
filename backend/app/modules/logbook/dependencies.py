"""FastAPI wiring for the logbook."""

from typing import Annotated

from fastapi import Depends

from app.core.database import SessionDep
from app.modules.logbook.service import LogbookService


def get_logbook_service(session: SessionDep) -> LogbookService:
    return LogbookService(session)


LogbookDep = Annotated[LogbookService, Depends(get_logbook_service)]
