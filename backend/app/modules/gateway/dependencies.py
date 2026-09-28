"""
FastAPI wiring for the gateway.

Assembles a `GatewayService` from the process container (Valkey pool, session factory,
settings) and the request's registry service. Workers build the same service directly
from their own container, so request handlers and background jobs share one code path.
"""

from typing import Annotated

from fastapi import Depends

from app.core.container import Container, ContainerDep
from app.core.database import SessionDep
from app.modules.gateway.history import CallHistoryService
from app.modules.gateway.plugins.rate_limiter import ValkeyRateLimiter
from app.modules.gateway.service import GatewayService, adaptive_policy
from app.modules.registry.dependencies import RegistryServiceDep
from app.modules.registry.service import RegistryService


def build_gateway(container: Container, registry: RegistryService) -> GatewayService:
    settings = container.settings
    limiter = ValkeyRateLimiter(
        container.valkey,
        adaptive_policy(settings),
        settings.rate_limit_acquire_timeout_s,
        settings.rate_limit_state_ttl_s,
    )
    return GatewayService(registry, limiter, container.database.sessions, settings)


def get_gateway(container: ContainerDep, registry: RegistryServiceDep) -> GatewayService:
    return build_gateway(container, registry)


def get_call_history(session: SessionDep) -> CallHistoryService:
    return CallHistoryService(session)


GatewayDep = Annotated[GatewayService, Depends(get_gateway)]
CallHistoryDep = Annotated[CallHistoryService, Depends(get_call_history)]
