"""
FastAPI wiring for the auth service.

Builds an `AuthService` per request from the process container and the request's
database session. Other modules' routers and dependencies use `AuthServiceDep` when they
need membership checks; they never touch the auth repository or tables.
"""

from typing import Annotated

from fastapi import Depends

from app.core.container import ContainerDep
from app.core.database import SessionDep
from app.core.throttle import FixedWindowLimiter
from app.modules.auth.service import AuthService


def get_auth_service(session: SessionDep, container: ContainerDep) -> AuthService:
    throttle = FixedWindowLimiter(container.valkey)
    return AuthService(session, container.passwords, container.access_tokens, container.settings, throttle)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
