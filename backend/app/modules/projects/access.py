"""
The one place roles are enforced (ADR 0029).

`enforce_permissions` is registered once, where the routers are included (`app/api.py`), so it runs before every
handler of the API. It looks the request up in the permission table (`app.core.permissions`) by method and path
template, signs the caller in, checks the token's scope, finds the caller's role in the workspace the path names
(`organization_id`, or the workspace of `project_id`) and refuses when the role is too low. A route that the table
does not cover is refused too (it fails closed), and `check_permission_coverage` lists such routes at start-up.
A workspace or project the caller is not a member of is reported as not found, so ids can't be probed.
"""

import logging
import uuid
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.database import SessionDep
from app.core.errors import NotFound, PermissionDenied
from app.core.permissions import (
    PERMISSIONS,
    UnmappedRoute,
    permission_action,
    role_allows,
    scope_allows,
    unmapped_paths,
)
from app.core.security import get_principal
from app.modules.auth.dependencies import AuthServiceDep
from app.modules.projects.repository import ProjectRepository

log = logging.getLogger(__name__)
_bearer = HTTPBearer(auto_error=False)

WORKSPACE_NOT_FOUND = "This workspace doesn't exist or you aren't a member of it."
PROJECT_HIDDEN = "This project doesn't exist or you don't have access to it."
NOT_COVERED = "This request isn't available. It has not been given a permission yet."
READ_ONLY_TOKEN = "This API token is read-only, so it can't {what}. Use a token with write access."
ROLE_TOO_LOW = "Your role in this workspace ({role}) can't {what}. Ask an owner or admin of the workspace."


async def enforce_permissions(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    session: SessionDep,
    auth: AuthServiceDep,
) -> None:
    route = request.scope.get("route")
    template = str(getattr(route, "path_format", None) or request.url.path)
    try:
        action = permission_action(request.method, template)
    except UnmappedRoute as exc:
        log.warning("route has no permission: %s", exc)
        raise PermissionDenied(NOT_COVERED) from exc
    if action is None:
        return
    principal = await get_principal(request, credentials)
    permission = PERMISSIONS[action]
    if not scope_allows(principal.scope, action):
        raise PermissionDenied(READ_ONLY_TOKEN.format(what=permission.wording))
    organization_id = await _organization_of(request.path_params, ProjectRepository(session))
    if organization_id is None:
        return
    role = await auth.role_in(principal.user_id, organization_id)
    if role is None:
        hidden = "project_id" in request.path_params
        raise NotFound(PROJECT_HIDDEN if hidden else WORKSPACE_NOT_FOUND)
    if not role_allows(role, action):
        raise PermissionDenied(ROLE_TOO_LOW.format(role=role.value, what=permission.wording))


async def _organization_of(params: dict[str, Any], projects: ProjectRepository) -> uuid.UUID | None:
    try:
        if "organization_id" in params:
            return uuid.UUID(str(params["organization_id"]))
        if "project_id" in params:
            return await projects.organization_id_of(uuid.UUID(str(params["project_id"])))
    except ValueError:
        return None  # not an id: the route's own validation answers with the usual message
    return None


def route_operations(app: FastAPI) -> list[tuple[str, str]]:
    """Every (method, path template) the API serves, from its OpenAPI description, without the version prefix."""
    return [(method.upper(), path) for path, methods in app.openapi().get("paths", {}).items() for method in methods]


def check_permission_coverage(app: FastAPI, api_prefix: str) -> list[str]:
    """Routes under the API prefix that no permission rule covers; logged as a warning at start-up."""
    stripped = [
        (method, path.removeprefix(api_prefix)) for method, path in route_operations(app) if path.startswith(api_prefix)
    ]
    missing = unmapped_paths(stripped)
    if missing:
        log.warning("These routes have no permission and are refused until they get one: %s", ", ".join(missing))
    return missing
