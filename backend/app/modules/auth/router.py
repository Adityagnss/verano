"""
Auth HTTP routes.

Sign-up and sign-in return the access token in the body and set the refresh token as an
httpOnly, Secure, SameSite=Strict cookie scoped to the refresh path only, so the browser
sends it nowhere else. `POST /auth/refresh` rotates it; `DELETE /auth/refresh` is logout
(revokes the token family and clears the cookie). Both live on the refresh path because
that is the only path the cookie is sent to.
"""

import uuid

from fastapi import APIRouter, Request, Response, status

from app.core.client_ip import ClientIP
from app.core.config import Settings
from app.core.container import SettingsDep
from app.core.security import CurrentPrincipal
from app.modules.auth.dependencies import AuthServiceDep
from app.modules.auth.schemas import (
    ApiTokenCreate,
    ApiTokenCreated,
    ApiTokenOut,
    AuthConfigOut,
    LoginRequest,
    MeOut,
    SessionOut,
    SignupRequest,
)
from app.modules.auth.service import IssuedSession

REFRESH_PATH = "/auth/refresh"

router = APIRouter(prefix="/auth", tags=["auth"])


def _cookie_path(settings: Settings) -> str:
    return f"{settings.api_prefix}{REFRESH_PATH}"


def _set_refresh_cookie(response: Response, issued: IssuedSession, settings: Settings) -> SessionOut:
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=issued.refresh_token,
        expires=issued.refresh_expires_at,
        path=_cookie_path(settings),
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite="strict",
    )
    return issued.body


def _refresh_cookie(request: Request, settings: Settings) -> str | None:
    return request.cookies.get(settings.refresh_cookie_name)


@router.get("/config")
async def auth_config(service: AuthServiceDep) -> AuthConfigOut:
    return await service.config()


@router.post("/signup", status_code=status.HTTP_201_CREATED)
async def signup(
    body: SignupRequest, ip: ClientIP, response: Response, service: AuthServiceDep, settings: SettingsDep
) -> SessionOut:
    return _set_refresh_cookie(response, await service.signup(body, ip), settings)


@router.post("/login")
async def login(
    body: LoginRequest, ip: ClientIP, response: Response, service: AuthServiceDep, settings: SettingsDep
) -> SessionOut:
    return _set_refresh_cookie(response, await service.login(body, ip), settings)


@router.post(REFRESH_PATH.removeprefix(router.prefix))
async def refresh(
    request: Request, ip: ClientIP, response: Response, service: AuthServiceDep, settings: SettingsDep
) -> SessionOut:
    return _set_refresh_cookie(response, await service.refresh(_refresh_cookie(request, settings), ip), settings)


@router.delete(REFRESH_PATH.removeprefix(router.prefix), status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response, service: AuthServiceDep, settings: SettingsDep) -> None:
    await service.logout(_refresh_cookie(request, settings))
    response.delete_cookie(
        settings.refresh_cookie_name,
        path=_cookie_path(settings),
        secure=settings.refresh_cookie_secure,
        httponly=True,
        samesite="strict",
    )


@router.get("/me")
async def me(principal: CurrentPrincipal, service: AuthServiceDep) -> MeOut:
    return await service.me(principal)


@router.post("/tokens", status_code=status.HTTP_201_CREATED)
async def create_token(body: ApiTokenCreate, principal: CurrentPrincipal, service: AuthServiceDep) -> ApiTokenCreated:
    return await service.create_api_token(principal, body)


@router.get("/tokens")
async def list_tokens(principal: CurrentPrincipal, service: AuthServiceDep) -> list[ApiTokenOut]:
    return await service.list_api_tokens(principal)


@router.delete("/tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_token(token_id: uuid.UUID, principal: CurrentPrincipal, service: AuthServiceDep) -> None:
    await service.revoke_api_token(principal, token_id)
