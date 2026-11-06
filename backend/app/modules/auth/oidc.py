"""
Sign in with an identity provider (Google, Microsoft or any OpenID Connect provider), ADR 0029.

The flow is the authorization-code flow with PKCE. `start` makes a random state, nonce and PKCE verifier, keeps
them in Valkey for ten minutes (they can be used once) and returns the provider's sign-in address. `finish` gets
the provider's answer: it takes the state back out (a state that was never issued, or already used, is refused),
swaps the code for tokens, checks the ID token's signature against the provider's published keys and its claims
with `oidc_domain.claims_problem` (issuer, audience, expiry, nonce, verified email), then finds or creates the
person. Accounts are matched by the provider's own subject id first, then by verified email. A new person gets
a personal workspace and, when the provider is set to a workspace, a membership with the mapped role.
No password is ever stored for a person who only signs in this way.
"""

import json
import secrets
import time
import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any
from urllib.parse import urlencode

import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.container import Container
from app.core.errors import AuthenticationFailed, NotFound, ValidationFailed
from app.core.permissions import Role
from app.core.security import utcnow
from app.modules.audit.schemas import AuditAction
from app.modules.audit.service import AuditLog
from app.modules.auth.domain import normalize_email
from app.modules.auth.oidc_domain import (
    ALLOWED_ALGORITHMS,
    ProviderConfig,
    claims_problem,
    configured_providers,
    make_pkce,
    mapped_role,
)
from app.modules.auth.repository import AuthRepository
from app.modules.auth.service import AuthService, IssuedSession

UNKNOWN_PROVIDER = "This sign-in method isn't set up on this server."
STATE_LOST = "This sign-in attempt expired or was already used. Start again."
PROVIDER_DOWN = "The sign-in provider didn't answer. Try again in a moment."
PROVIDER_REFUSED = "The provider refused the sign-in: {reason}"
TOKEN_BAD = "The provider's sign-in answer could not be checked. Try again."
DISCOVERY_TTL_S = 3600.0
STATE_KEY = "oidc:state:{state}"

_discovery_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_jwks_cache: dict[str, tuple[float, dict[str, Any]]] = {}


class OidcService:
    def __init__(
        self,
        session: AsyncSession,
        auth: AuthService,
        container: Container,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._repo = AuthRepository(session)
        self._auth = auth
        self._container = container
        self._settings = container.settings
        self._audit = AuditLog(session, container.settings)
        self._clock = clock

    def redirect_uri(self, name: str) -> str:
        base = self._settings.public_url.rstrip("/")
        return f"{base}{self._settings.api_prefix}/auth/oidc/{name}/callback"

    async def start(self, name: str) -> str:
        config = self._provider(name)
        discovery = await self._discovery(config)
        state, nonce, pkce = secrets.token_urlsafe(32), secrets.token_urlsafe(32), make_pkce()
        record = json.dumps({"provider": name, "nonce": nonce, "verifier": pkce.verifier})
        await self._container.valkey.set(STATE_KEY.format(state=state), record, ex=self._settings.oidc_state_ttl_s)
        query = {
            "response_type": "code",
            "client_id": config.client_id,
            "redirect_uri": self.redirect_uri(name),
            "scope": " ".join(config.scopes),
            "state": state,
            "nonce": nonce,
            "code_challenge": pkce.challenge,
            "code_challenge_method": "S256",
        }
        return f"{discovery['authorization_endpoint']}?{urlencode(query)}"

    async def finish(self, name: str, code: str | None, state: str | None, error: str | None) -> IssuedSession:
        config = self._provider(name)
        if error:
            raise AuthenticationFailed(PROVIDER_REFUSED.format(reason=error))
        if not code or not state:
            raise AuthenticationFailed(STATE_LOST)
        raw = await self._container.valkey.getdel(STATE_KEY.format(state=state))
        if raw is None:
            raise AuthenticationFailed(STATE_LOST)
        saved = json.loads(raw)
        if saved.get("provider") != name:
            raise AuthenticationFailed(STATE_LOST)
        discovery = await self._discovery(config)
        id_token = await self._exchange(config, discovery, code, saved["verifier"])
        claims = await self._verified_claims(config, discovery, id_token)
        problem = claims_problem(config, str(discovery.get("issuer", "")), claims, saved["nonce"], self._clock())
        if problem:
            raise AuthenticationFailed(problem)
        user_id = await self._person(config, claims)
        user = await self._repo.user(user_id)
        if user is None:
            raise NotFound("This account no longer exists.")
        return await self._auth.issue_session(user)

    # --- the provider ------------------------------------------------------------------------------

    def _provider(self, name: str) -> ProviderConfig:
        found = next((p for p in configured_providers(self._settings) if p.name == name), None)
        if found is None:
            raise NotFound(UNKNOWN_PROVIDER)
        return found

    async def _get_json(self, url: str) -> dict[str, Any]:
        try:
            response = await self._container.http.get(url, timeout=self._settings.oidc_http_timeout_s)
            response.raise_for_status()
            body = response.json()
        except Exception as exc:
            raise AuthenticationFailed(PROVIDER_DOWN) from exc
        if not isinstance(body, dict):
            raise AuthenticationFailed(PROVIDER_DOWN)
        return body

    async def _discovery(self, config: ProviderConfig) -> dict[str, Any]:
        cached = _discovery_cache.get(config.discovery_url)
        if cached and time.monotonic() - cached[0] < DISCOVERY_TTL_S:
            return cached[1]
        document = await self._get_json(config.discovery_url)
        for needed in ("authorization_endpoint", "token_endpoint", "jwks_uri", "issuer"):
            if not document.get(needed):
                raise AuthenticationFailed(PROVIDER_DOWN)
        _discovery_cache[config.discovery_url] = (time.monotonic(), document)
        return document

    async def _exchange(self, config: ProviderConfig, discovery: dict[str, Any], code: str, verifier: str) -> str:
        form = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri(config.name),
            "client_id": config.client_id,
            "client_secret": config.client_secret,
            "code_verifier": verifier,
        }
        try:
            response = await self._container.http.post(
                discovery["token_endpoint"], data=form, timeout=self._settings.oidc_http_timeout_s
            )
        except Exception as exc:
            raise AuthenticationFailed(PROVIDER_DOWN) from exc
        if response.status_code >= 400:
            raise AuthenticationFailed(PROVIDER_REFUSED.format(reason="the sign-in code was not accepted."))
        token = response.json().get("id_token") if response.content else None
        if not isinstance(token, str):
            raise AuthenticationFailed(TOKEN_BAD)
        return token

    async def _verified_claims(self, config: ProviderConfig, discovery: dict[str, Any], token: str) -> dict[str, Any]:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise AuthenticationFailed(TOKEN_BAD) from exc
        algorithm = header.get("alg")
        offered = discovery.get("id_token_signing_alg_values_supported") or ALLOWED_ALGORITHMS
        if algorithm not in ALLOWED_ALGORITHMS or algorithm not in offered:
            raise AuthenticationFailed(TOKEN_BAD)
        key = await self._signing_key(discovery["jwks_uri"], header.get("kid"))
        try:
            claims = jwt.decode(
                token,
                key,
                algorithms=[algorithm],
                options={"verify_aud": False, "verify_iss": False, "verify_exp": False, "require": ["sub"]},
            )
        except jwt.PyJWTError as exc:
            raise AuthenticationFailed(TOKEN_BAD) from exc
        return dict(claims)

    async def _signing_key(self, jwks_uri: str, kid: str | None) -> Any:
        for refresh in (False, True):
            cached = _jwks_cache.get(jwks_uri)
            if refresh or cached is None or time.monotonic() - cached[0] > DISCOVERY_TTL_S:
                cached = (time.monotonic(), await self._get_json(jwks_uri))
                _jwks_cache[jwks_uri] = cached
            for entry in cached[1].get("keys", []):
                if isinstance(entry, dict) and entry.get("kid") == kid and entry.get("use", "sig") == "sig":
                    return jwt.PyJWK(entry).key
        raise AuthenticationFailed(TOKEN_BAD)

    # --- the person --------------------------------------------------------------------------------

    async def _person(self, config: ProviderConfig, claims: dict[str, Any]) -> uuid.UUID:
        now = self._clock()
        subject = str(claims["sub"])
        email = normalize_email(str(claims.get("email") or claims.get("preferred_username")))
        name = str(claims.get("name") or email.split("@")[0])[:120]
        identity = await self._repo.identity(config.name, subject)
        user = await self._repo.user(identity.user_id) if identity else await self._repo.user_by_email(email)
        if user is None:
            if not self._settings.allow_signup and await self._repo.has_users() and not config.organization_id:
                raise ValidationFailed("Sign-up is turned off on this server. Ask its administrator for an account.")
            org_name = self._settings.personal_org_name_template.format(name=name)
            user = await self._repo.create_external_user(
                email, name, self._auth.unusable_password_hash(), org_name, now
            )
        elif not user.email_verified:
            await self._repo.mark_verified(user.id, now)
        if identity is None:
            await self._repo.add_identity(user.id, config.name, subject, email)
        await self._join_workspace(config, claims, user.id, user.email)
        return user.id

    async def _join_workspace(
        self, config: ProviderConfig, claims: dict[str, Any], user_id: uuid.UUID, email: str
    ) -> None:
        if not config.organization_id:
            return
        organization_id = uuid.UUID(config.organization_id)
        if await self._repo.organization(organization_id) is None:
            return
        mapped = mapped_role(config, claims)
        current = await self._repo.role_in(user_id, organization_id)
        if current is None:
            role = mapped or config.default_role
            await self._repo.add_membership(organization_id, user_id, role)
            await self._audit.record(
                organization_id=organization_id,
                actor_id=user_id,
                action=AuditAction.MEMBER_JOINED,
                summary=f"{email} signed in with {config.title} and joined as {role.value}.",
                target_type="user",
                target_id=user_id,
                details={"role": role.value, "provider": config.name},
            )
        elif mapped is not None and mapped is not current and current is not Role.OWNER:
            await self._repo.set_role(organization_id, user_id, mapped)
            await self._audit.record(
                organization_id=organization_id,
                actor_id=user_id,
                action=AuditAction.ROLE_CHANGED,
                summary=f"{email}'s role became {mapped.value} from their {config.title} groups.",
                target_type="user",
                target_id=user_id,
                details={"from": current.value, "to": mapped.value, "provider": config.name},
            )
