"""
Typed errors and their single mapping to HTTP responses.

Every failure the API can report is a subclass of `AppError` carrying its own status code,
machine-readable code and retry semantics as class attributes, so mapping and retry
decisions are table lookups rather than branches. `install_error_handlers` is called once
by the app factory and renders every error in the one documented format:
`{"error": {"code": str, "message": str, "details": object}}`, plus a `Retry-After`
header whenever the error says when trying again makes sense.
"""

import math
from typing import Any, ClassVar

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppError(Exception):
    status_code: ClassVar[int] = 500
    code: ClassVar[str] = "internal_error"
    retryable: ClassVar[bool] = False

    def __init__(self, message: str, details: dict[str, Any] | None = None, retry_after_s: float | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}
        self.retry_after_s = retry_after_s


class NotFound(AppError):
    status_code = 404
    code = "not_found"


class Conflict(AppError):
    status_code = 409
    code = "conflict"


class ValidationFailed(AppError):
    status_code = 422
    code = "validation_failed"


class AuthenticationFailed(AppError):
    status_code = 401
    code = "authentication_failed"


class PermissionDenied(AppError):
    status_code = 403
    code = "permission_denied"


class InvalidTransition(AppError):
    status_code = 409
    code = "invalid_transition"


class TooManyRequests(AppError):
    status_code = 429
    code = "too_many_requests"


class InvalidParameter(AppError):
    status_code = 422
    code = "invalid_parameter"


class ProviderError(AppError):
    status_code = 502
    code = "provider_error"

    def __init__(
        self,
        message: str,
        details: dict[str, Any] | None = None,
        retry_after_s: float | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message, details, retry_after_s)
        self.headers = headers or {}


class ProviderAuthError(ProviderError):
    status_code = 400
    code = "provider_auth_error"


class ProviderBadRequest(ProviderError):
    status_code = 400
    code = "provider_bad_request"


class ContentPolicyBlocked(ProviderError):
    status_code = 400
    code = "content_policy_blocked"


class ModelNotFound(ProviderError):
    status_code = 404
    code = "model_not_found"


class RateLimited(ProviderError):
    status_code = 429
    code = "rate_limited"
    retryable = True


class ProviderUnavailable(ProviderError):
    status_code = 503
    code = "provider_unavailable"
    retryable = True


class ProviderTimeout(ProviderError):
    status_code = 504
    code = "provider_timeout"
    retryable = True


class CircuitOpen(ProviderUnavailable):
    """The provider has been failing, so calls to it are paused for a short while (never retried at once)."""

    code = "circuit_open"
    retryable = False


class StructuredOutputError(AppError):
    status_code = 502
    code = "structured_output_error"


PROVIDER_MESSAGES: dict[type[ProviderError], str] = {
    ProviderAuthError: "This key was rejected by {provider}. Check that it's active and try again.",
    RateLimited: "{provider} is rate limiting this key. Wait a moment and try again.",
    ProviderUnavailable: "{provider} isn't responding right now. Try again in a few minutes.",
    ProviderTimeout: "{provider} took too long to answer. Try again.",
    ModelNotFound: "{provider} couldn't find what was requested: {detail}",
    ContentPolicyBlocked: "{provider} blocked this request under its content policy: {detail}",
    ProviderBadRequest: "{provider} rejected the request: {detail}",
}


def provider_error(
    error_cls: type[ProviderError],
    provider: str,
    detail: str,
    retry_after_s: float | None = None,
    headers: dict[str, str] | None = None,
) -> ProviderError:
    message = PROVIDER_MESSAGES[error_cls].format(provider=provider, detail=detail)
    return error_cls(message, {"provider_message": detail}, retry_after_s=retry_after_s, headers=headers)


def parse_retry_after(value: str | None) -> float | None:
    try:
        return max(float(value), 0.0) if value is not None else None
    except ValueError:
        return None


def error_body(code: str, message: str, details: Any) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details}}


async def _app_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    headers = {"Retry-After": str(math.ceil(exc.retry_after_s))} if exc.retry_after_s is not None else None
    return JSONResponse(error_body(exc.code, exc.message, exc.details), exc.status_code, headers=headers)


async def _validation_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    details = [{"field": ".".join(str(p) for p in err["loc"]), "message": err["msg"]} for err in exc.errors()]
    body = error_body(ValidationFailed.code, "The request is not valid.", details)
    return JSONResponse(body, ValidationFailed.status_code)


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_handler)
