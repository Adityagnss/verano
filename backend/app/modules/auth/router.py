"""
Auth HTTP routes.

Sign-up and sign-in return the access token in the body and set the refresh token as an
httpOnly, Secure, SameSite=Strict cookie scoped to the refresh path only, so the browser
sends it nowhere else. `POST /auth/refresh` rotates it; `DELETE /auth/refresh` is logout
(revokes the token family and clears the cookie). Both live on the refresh path because
that is the only path the cookie is sent to.
"""

import uuid
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Query, Request, Response, status
from fastapi.responses import RedirectResponse

from app.core.client_ip import ClientIP
from app.core.config import Settings
from app.core.container import SettingsDep
from app.core.errors import AppError
from app.core.security import CurrentPrincipal
from app.modules.auth.dependencies import AuthServiceDep, OidcServiceDep
from app.modules.auth.schemas import (
    ApiTokenCreate,
    ApiTokenCreated,
    ApiTokenOut,
    AuthConfigOut,
    InvitePreview,
    LoginRequest,
    MeOut,
    OidcStart,
    OrganizationOut,
    SessionOut,
    SignupRequest,
    VerifyEmailRequest,
)
from app.modules.auth.service import IssuedSession
from app.modules.projects.dependencies import ProjectServiceDep

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


@router.get("/oidc/{provider}/start")
async def oidc_start(provider: str, oidc: OidcServiceDep) -> OidcStart:
    """The address to send the browser to, to sign in with this provider."""
    return OidcStart(authorization_url=await oidc.start(provider))


@router.get("/oidc/{provider}/callback", include_in_schema=False)
async def oidc_callback(
    provider: str,
    oidc: OidcServiceDep,
    settings: SettingsDep,
    code: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    error: Annotated[str | None, Query()] = None,
) -> RedirectResponse:
    """Where the provider sends the browser back. On success the refresh cookie is set and the browser goes on to the
    app, which then asks for its access token; on failure it goes to the sign-in page with the reason."""
    base = settings.public_url.rstrip("/")
    try:
        issued = await oidc.finish(provider, code, state, error)
    except AppError as exc:
        return RedirectResponse(f"{base}/login?{urlencode({'error': exc.message})}", status_code=303)
    redirect = RedirectResponse(f"{base}/signin/complete", status_code=303)
    _set_refresh_cookie(redirect, issued, settings)
    return redirect


@router.post("/verify-email", status_code=status.HTTP_204_NO_CONTENT)
async def verify_email(body: VerifyEmailRequest, service: AuthServiceDep) -> None:
    await service.members.verify_email(body.token)


@router.post("/resend-verification", status_code=status.HTTP_204_NO_CONTENT)
async def resend_verification(principal: CurrentPrincipal, service: AuthServiceDep) -> None:
    await service.members.resend_verification(principal)


@router.get("/invites/{token}")
async def preview_invite(token: str, service: AuthServiceDep) -> InvitePreview:
    """What an invite link is for, shown before the person signs in or up."""
    return await service.members.preview(token)


@router.post("/invites/{token}/accept")
async def accept_invite(token: str, principal: CurrentPrincipal, service: AuthServiceDep) -> OrganizationOut:
    organization_id = await service.members.accept(principal, token)
    return next(o for o in await service.organizations(principal.user_id) if o.id == organization_id)


@router.get("/me")
async def me(principal: CurrentPrincipal, service: AuthServiceDep) -> MeOut:
    return await service.me(principal)


@router.post("/tokens", status_code=status.HTTP_201_CREATED)
async def create_token(
    body: ApiTokenCreate, principal: CurrentPrincipal, service: AuthServiceDep, projects: ProjectServiceDep
) -> ApiTokenCreated:
    if body.project_id is not None:  # a token can only be limited to a project you can open
        await projects.require_access(principal, body.project_id)
    return await service.create_api_token(principal, body)


@router.get("/tokens")
async def list_tokens(principal: CurrentPrincipal, service: AuthServiceDep) -> list[ApiTokenOut]:
    return await service.list_api_tokens(principal)


@router.delete("/tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_token(token_id: uuid.UUID, principal: CurrentPrincipal, service: AuthServiceDep) -> None:
    await service.revoke_api_token(principal, token_id)
