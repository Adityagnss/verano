"""
Security primitives: passwords, tokens, secret encryption and the request principal.

- Passwords are hashed with Argon2id (argon2-cffi defaults, tuned by the library).
- Access tokens are short-lived HS256 JWTs carrying only the user id; the frontend keeps
  them in memory. Refresh tokens are opaque random strings; only their SHA-256 digest is
  stored, which is safe because they have 256 bits of entropy.
- Provider API keys are encrypted with Fernet. `VERANO_MASTER_KEYS` holds one or more
  comma-separated keys; the first encrypts, all decrypt, so keys can be rotated.
`CurrentPrincipal` is the dependency every protected route uses.
"""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Protocol

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings
from app.core.errors import AppError, AuthenticationFailed
from app.core.permissions import TokenScope

_bearer = HTTPBearer(auto_error=False)


class SecretDecryptionFailed(AppError):
    code = "secret_decryption_failed"


API_TOKEN_PREFIX = "vrn_"


@dataclass(frozen=True)
class Principal:
    user_id: uuid.UUID
    via_api_token: bool = False
    scope: TokenScope = TokenScope.WRITE


class ApiTokenVerifier(Protocol):
    """Turns a personal API token into its owner. Implemented by the auth module and set on
    the container at startup, so this file never imports a module."""

    async def verify(self, raw_token: str) -> Principal: ...


class Passwords:
    def __init__(self) -> None:
        self._hasher = PasswordHasher()
        self._dummy_hash = self._hasher.hash(secrets.token_urlsafe(16))

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, password_hash: str | None, password: str) -> bool:
        try:
            self._hasher.verify(password_hash or self._dummy_hash, password)
        except (VerificationError, InvalidHashError):
            return False
        return password_hash is not None


class AccessTokens:
    def __init__(self, settings: Settings) -> None:
        self._secret = settings.jwt_secret.get_secret_value()
        self._algorithm = settings.jwt_algorithm
        self.ttl_s = settings.access_token_ttl_s

    def issue(self, user_id: uuid.UUID, now: datetime) -> str:
        claims = {"sub": str(user_id), "iat": now, "exp": now + timedelta(seconds=self.ttl_s), "typ": "access"}
        return jwt.encode(claims, self._secret, algorithm=self._algorithm)

    def verify(self, token: str) -> Principal:
        try:
            claims = jwt.decode(token, self._secret, algorithms=[self._algorithm], options={"require": ["exp", "sub"]})
        except jwt.PyJWTError as exc:
            raise AuthenticationFailed("Your session has expired. Please sign in again.") from exc
        if claims.get("typ") != "access":
            raise AuthenticationFailed("Your session has expired. Please sign in again.")
        return Principal(user_id=uuid.UUID(claims["sub"]))


def new_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def digest_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class SecretBox:
    def __init__(self, settings: Settings) -> None:
        keys = [key.strip() for key in settings.master_keys.get_secret_value().split(",") if key.strip()]
        if not keys:
            raise ValueError("VERANO_MASTER_KEYS must contain at least one Fernet key")
        self._fernet = MultiFernet([Fernet(key) for key in keys])

    def encrypt(self, plaintext: str) -> bytes:
        return self._fernet.encrypt(plaintext.encode())

    def decrypt(self, ciphertext: bytes) -> str:
        try:
            return self._fernet.decrypt(ciphertext).decode()
        except InvalidToken as exc:
            raise SecretDecryptionFailed(
                "A stored key could not be decrypted with the configured master keys."
            ) from exc


def utcnow() -> datetime:
    return datetime.now(UTC)


async def get_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Principal:
    cached: Principal | None = getattr(request.state, "principal", None)
    if cached is not None:  # the permission check at the router level already signed this request in
        return cached
    if credentials is None:
        raise AuthenticationFailed("Please sign in to continue.")
    container = request.app.state.container
    if credentials.credentials.startswith(API_TOKEN_PREFIX):
        if container.api_tokens is None:
            raise AuthenticationFailed("API tokens are not available.")
        principal: Principal = await container.api_tokens.verify(credentials.credentials)
    else:
        tokens: AccessTokens = container.access_tokens
        principal = tokens.verify(credentials.credentials)
    request.state.principal = principal
    return principal


CurrentPrincipal = Annotated[Principal, Depends(get_principal)]
