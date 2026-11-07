"""
A fake OpenID Connect provider for the sign-in tests: a small ASGI app with discovery, the signing keys and a
token endpoint. It checks what a real provider checks (client, redirect address, PKCE) and signs ID tokens with a
real RSA key, so the app under test does real signature verification. Each test says what the next token
contains through `claims` and the flags, to produce the bad tokens that must be refused.
"""

import base64
import hashlib
import secrets
import time
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

ISSUER = "https://idp.test"
CLIENT_ID = "verano-client"
CLIENT_SECRET = "verano-secret"
KID = "key-1"

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _jwks() -> dict[str, Any]:
    public = jwt.algorithms.RSAAlgorithm.to_jwk(_KEY.public_key(), as_dict=True)
    return {"keys": [{**public, "kid": KID, "use": "sig", "alg": "RS256"}]}


class FakeIdP:
    def __init__(self) -> None:
        self.codes: dict[str, dict[str, Any]] = {}
        self.token_requests: list[dict[str, str]] = []
        self.sign_with_other_key = False
        self.fail_token_endpoint = False
        self.app = Starlette(
            routes=[
                Route("/.well-known/openid-configuration", self.discovery),
                Route("/keys", self.keys),
                Route("/token", self.token, methods=["POST"]),
            ]
        )

    async def discovery(self, request: Request) -> Response:
        return JSONResponse(
            {
                "issuer": ISSUER,
                "authorization_endpoint": f"{ISSUER}/authorize",
                "token_endpoint": f"{ISSUER}/token",
                "jwks_uri": f"{ISSUER}/keys",
                "id_token_signing_alg_values_supported": ["RS256"],
            }
        )

    async def keys(self, request: Request) -> Response:
        return JSONResponse(_jwks())

    def authorize(self, authorization_url: str, **claims: Any) -> str:
        """What the person does at the provider: log in and consent. Returns the code the browser brings back.
        `claims` replace or add to the ID token's claims (a value of None removes one)."""
        from urllib.parse import parse_qs, urlparse

        query = {k: v[0] for k, v in parse_qs(urlparse(authorization_url).query).items()}
        assert query["response_type"] == "code"
        assert query["code_challenge_method"] == "S256"
        assert query["client_id"] == CLIENT_ID
        assert "openid" in query["scope"].split()
        code = secrets.token_urlsafe(16)
        self.codes[code] = {"query": query, "claims": claims}
        return code

    async def token(self, request: Request) -> Response:
        form = dict((await request.form()).items())
        self.token_requests.append({k: str(v) for k, v in form.items()})
        if self.fail_token_endpoint:
            return JSONResponse({"error": "server_error"}, status_code=500)
        issued = self.codes.pop(str(form.get("code")), None)
        if issued is None:
            return JSONResponse({"error": "invalid_grant"}, status_code=400)
        query = issued["query"]
        if form.get("client_id") != CLIENT_ID or form.get("client_secret") != CLIENT_SECRET:
            return JSONResponse({"error": "invalid_client"}, status_code=401)
        if form.get("redirect_uri") != query["redirect_uri"]:
            return JSONResponse({"error": "invalid_grant"}, status_code=400)
        digest = hashlib.sha256(str(form.get("code_verifier")).encode()).digest()
        if base64.urlsafe_b64encode(digest).rstrip(b"=").decode() != query["code_challenge"]:
            return JSONResponse({"error": "invalid_grant", "error_description": "PKCE failed"}, status_code=400)
        now = int(time.time())
        claims: dict[str, Any] = {
            "iss": ISSUER,
            "aud": CLIENT_ID,
            "sub": "subject-1",
            "email": "ada@corp.example",
            "email_verified": True,
            "name": "Ada Lovelace",
            "nonce": query["nonce"],
            "iat": now,
            "exp": now + 300,
        }
        for name, value in issued["claims"].items():
            if value is None:
                claims.pop(name, None)
            else:
                claims[name] = value
        key = _OTHER_KEY if self.sign_with_other_key else _KEY
        token = jwt.encode(claims, key, algorithm="RS256", headers={"kid": KID})
        return JSONResponse({"id_token": token, "access_token": "unused", "token_type": "Bearer"})
