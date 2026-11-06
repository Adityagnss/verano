"""FastAPI wiring for the apps service."""

from typing import Annotated

from fastapi import Depends

from app.core.container import ContainerDep
from app.core.database import SessionDep
from app.modules.apps.service import AppService


def get_app_service(session: SessionDep, container: ContainerDep) -> AppService:
    return AppService(session, container)


AppServiceDep = Annotated[AppService, Depends(get_app_service)]
