"""
Process-wide infrastructure container.

Holds the objects that are expensive to create and safe to share: settings, the database
engine, the Valkey pool, the pooled HTTP client for provider APIs, and the security
primitives. The API lifespan and each worker build exactly one `Container` and close it
on shutdown. Module `dependencies.py` files read it from `request.app.state.container`
and assemble their services from it, so nothing opens connections per request.
"""

from dataclasses import dataclass
from typing import Annotated

import httpx
from fastapi import Depends, Request
from redis.asyncio import Redis

from app.core.config import Settings
from app.core.database import Database
from app.core.security import AccessTokens, Passwords, SecretBox
from app.core.valkey import create_valkey


@dataclass
class Container:
    settings: Settings
    database: Database
    valkey: Redis
    http: httpx.AsyncClient
    passwords: Passwords
    access_tokens: AccessTokens
    secret_box: SecretBox

    @classmethod
    def build(cls, settings: Settings) -> "Container":
        return cls(
            settings=settings,
            database=Database(settings),
            valkey=create_valkey(settings),
            http=httpx.AsyncClient(timeout=settings.provider_http_timeout_s),
            passwords=Passwords(),
            access_tokens=AccessTokens(settings),
            secret_box=SecretBox(settings),
        )

    async def close(self) -> None:
        await self.http.aclose()
        await self.valkey.aclose()
        await self.database.dispose()


def get_container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container


def get_app_settings(request: Request) -> Settings:
    return get_container(request).settings


ContainerDep = Annotated[Container, Depends(get_container)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]
