"""
Pure OpenID Connect rules: provider settings, the PKCE pair, the checks on an ID token's claims and the mapping
of the provider's groups to a role. No I/O; the service fetches and signs, this file decides.

Safety rules (ADR 0029): a sign-in is accepted only when the token is for this app (audience), from the expected
issuer, not expired, carries the nonce that was sent, and the provider says the email is verified. A role taken
from the provider's groups is never higher than admin; owners are made by owners.
"""

import base64
import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core.config import Settings
from app.core.permissions import ROLE_RANK, Role
from app.modules.auth.schemas import SignInProviderOut

GOOGLE_DISCOVERY = "https://accounts.google.com/.well-known/openid-configuration"
MICROSOFT_DISCOVERY = "https://login.microsoftonline.com/{tenant}/v2.0/.well-known/openid-configuration"
MICROSOFT_ANY_TENANTS = {"common", "organizations", "consumers"}
ALLOWED_ALGORITHMS = ("RS256", "RS384", "RS512", "ES256", "ES384", "PS256", "PS384", "PS512")
CLOCK_SKEW_S = 60
HIGHEST_MAPPED_ROLE = Role.ADMIN


class ProviderConfig(BaseModel):
    name: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,31}$")
    kind: Literal["google", "microsoft", "oidc"] = "oidc"
    display_name: str = ""
    client_id: str
    client_secret: str
    issuer: str = ""  # generic OIDC: the issuer address; Microsoft: the tenant id (blank = any work account)
    scopes: list[str] = ["openid", "email", "profile"]
    organization_id: str | None = None  # the workspace people join on first sign-in
    default_role: Role = Role.MEMBER
    roles_claim: str | None = None  # the token claim that lists the person's groups or roles
    role_map: dict[str, Role] = {}
    allowed_domains: list[str] = []

    @property
    def title(self) -> str:
        return self.display_name or {"google": "Google", "microsoft": "Microsoft"}.get(self.kind, self.name)

    @property
    def tenant(self) -> str:
        return self.issuer or "organizations"

    @property
    def discovery_url(self) -> str:
        if self.kind == "google":
            return GOOGLE_DISCOVERY
        if self.kind == "microsoft":
            return MICROSOFT_DISCOVERY.format(tenant=self.tenant)
        return self.issuer.rstrip("/") + "/.well-known/openid-configuration"


def configured_providers(settings: Settings) -> list[ProviderConfig]:
    return [ProviderConfig.model_validate(raw) for raw in settings.oidc_providers]


def provider_list(settings: Settings) -> list[SignInProviderOut]:
    return [SignInProviderOut(name=p.name, display_name=p.title, kind=p.kind) for p in configured_providers(settings)]


@dataclass(frozen=True)
class Pkce:
    verifier: str
    challenge: str


def make_pkce() -> Pkce:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return Pkce(verifier, base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii"))


def issuer_matches(config: ProviderConfig, discovered: str, claims: dict[str, Any]) -> bool:
    issuer = discovered
    if "{tenantid}" in issuer:  # Microsoft's multi-tenant metadata names the tenant in the token itself
        tenant = claims.get("tid")
        if not isinstance(tenant, str) or not tenant:
            return False
        issuer = issuer.replace("{tenantid}", tenant)
    return claims.get("iss") == issuer


def _verified_email(config: ProviderConfig, claims: dict[str, Any]) -> bool:
    if claims.get("email_verified") in (True, "true"):
        return True
    if config.kind == "microsoft":
        # Work accounts do not send email_verified. Microsoft's own "domain owner verified" flag counts, and so
        # does a sign-in to one named tenant, whose directory is controlled by the administrator.
        if claims.get("xms_edov") in (True, "true", 1, "1"):
            return True
        return config.tenant not in MICROSOFT_ANY_TENANTS and claims.get("tid") == config.tenant
    return False


def claims_problem(
    config: ProviderConfig, discovered_issuer: str, claims: dict[str, Any], nonce: str, now: datetime
) -> str | None:
    """Why this ID token must not be accepted, in plain words; None when it is fine."""
    if not issuer_matches(config, discovered_issuer, claims):
        return "The sign-in answer came from an unexpected provider."
    audience = claims.get("aud")
    audiences = audience if isinstance(audience, list) else [audience]
    if config.client_id not in audiences or (len(audiences) > 1 and claims.get("azp") != config.client_id):
        return "The sign-in answer was meant for a different app."
    expires = claims.get("exp")
    if not isinstance(expires, int | float) or now.timestamp() > expires + CLOCK_SKEW_S:
        return "The sign-in answer has expired. Try again."
    if not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
        return "The sign-in answer doesn't match this sign-in attempt. Try again."
    email = claims.get("email") or claims.get("preferred_username")
    if not isinstance(email, str) or "@" not in email:
        return "Your account at the provider has no email address, so we can't sign you in."
    if not _verified_email(config, claims):
        return "Your email address isn't verified at the provider. Verify it there and try again."
    if config.allowed_domains and email.rsplit("@", 1)[-1].lower() not in {d.lower() for d in config.allowed_domains}:
        return "Accounts with this email domain can't sign in here. Ask the workspace owner."
    if not isinstance(claims.get("sub"), str) or not claims["sub"]:
        return "The provider didn't identify you. Try again."
    return None


def mapped_role(config: ProviderConfig, claims: dict[str, Any]) -> Role | None:
    """The role the provider's groups give, never above admin; None when no claim is configured or none matches
    (the caller then uses the default role for new members and keeps the existing role otherwise)."""
    if not config.roles_claim:
        return None
    raw = claims.get(config.roles_claim)
    values = raw if isinstance(raw, list) else [raw]
    roles = [config.role_map[str(v)] for v in values if str(v) in config.role_map]
    if not roles:
        return None
    best = max(roles, key=lambda role: ROLE_RANK[role])
    return best if ROLE_RANK[best] <= ROLE_RANK[HIGHEST_MAPPED_ROLE] else HIGHEST_MAPPED_ROLE
