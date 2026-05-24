"""OpenAI-compatible error handling — exception classes + FastAPI handlers."""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from hubia.api.schemas import ErrorDetail, ErrorResponse


# ---------------------------------------------------------------------------
# Exception classes
# ---------------------------------------------------------------------------


class HubiaError(Exception):
    """Base exception for all Hubia API errors."""

    def __init__(
        self,
        message: str,
        code: str | None = None,
        type_: str = "invalid_request_error",
    ) -> None:
        self.message = message
        self.code = code
        self.type_ = type_
        super().__init__(message)


class AuthenticationError(HubiaError):
    """Invalid or missing authentication."""

    def __init__(self, message: str = "Authentication required") -> None:
        super().__init__(message, code="authentication_error", type_="authentication_error")


class SessionExpiredError(HubiaError):
    """Provider session expired — user must re-capture credentials."""

    def __init__(
        self,
        message: str = "Provider session expired. Please re-capture credentials via /sandbox",
    ) -> None:
        super().__init__(message, code="credential_expired", type_="invalid_request_error")


class ModelNotFoundError(HubiaError):
    """Requested model is not registered."""

    def __init__(self, model: str) -> None:
        super().__init__(
            f"Model '{model}' not found",
            code="model_not_found",
            type_="invalid_request_error",
        )


class CredentialMissingError(HubiaError):
    """User has no stored credentials for the requested provider."""

    def __init__(self, provider: str) -> None:
        super().__init__(
            f"No credentials found for provider '{provider}'. "
            f"Please capture via /sandbox",
            code="credential_missing",
            type_="invalid_request_error",
        )


class ProviderError(HubiaError):
    """Upstream provider error after retries are exhausted."""

    def __init__(self, message: str = "Provider request failed") -> None:
        super().__init__(message, code="provider_error", type_="api_error")


class RateLimitError(HubiaError):
    """Rate limit exceeded."""

    def __init__(self, message: str = "Rate limit exceeded") -> None:
        super().__init__(message, code="rate_limit_exceeded", type_="rate_limit_error")


# ---------------------------------------------------------------------------
# HTTP status mapping
# ---------------------------------------------------------------------------

_ERROR_STATUS_MAP: dict[type[HubiaError], int] = {
    AuthenticationError: status.HTTP_401_UNAUTHORIZED,
    SessionExpiredError: status.HTTP_403_FORBIDDEN,
    ModelNotFoundError: status.HTTP_404_NOT_FOUND,
    CredentialMissingError: status.HTTP_403_FORBIDDEN,
    ProviderError: status.HTTP_502_BAD_GATEWAY,
    RateLimitError: status.HTTP_429_TOO_MANY_REQUESTS,
}


def _error_response(err: HubiaError, http_status: int) -> JSONResponse:
    """Build an OpenAI-compatible error JSON response."""
    return JSONResponse(
        status_code=http_status,
        content=ErrorResponse(
            error=ErrorDetail(
                message=err.message,
                type=err.type_,
                code=err.code,
            )
        ).model_dump(mode="json"),
    )


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------


def _hubia_error_handler(request: Request, exc: HubiaError) -> JSONResponse:
    """Convert any :class:`HubiaError` to the correct HTTP response."""
    http_status = _ERROR_STATUS_MAP.get(type(exc), status.HTTP_500_INTERNAL_SERVER_ERROR)
    return _error_response(exc, http_status)


def _validation_error_handler(request: Request, exc: ValidationError) -> JSONResponse:
    """Convert Pydantic validation errors to OpenAI error format."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=ErrorResponse(
            error=ErrorDetail(
                message=str(exc),
                type="invalid_request_error",
                code="validation_error",
            )
        ).model_dump(mode="json"),
    )


def _general_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for unhandled exceptions — return 500."""
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            error=ErrorDetail(
                message="Internal server error",
                type="api_error",
                code="internal_error",
            )
        ).model_dump(mode="json"),
    )


# ---------------------------------------------------------------------------
# Registration helper
# ---------------------------------------------------------------------------


def register_error_handlers(app: FastAPI) -> None:
    """Register all custom error handlers on a FastAPI application."""
    app.add_exception_handler(HubiaError, _hubia_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(ValidationError, _validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _general_error_handler)  # type: ignore[arg-type]
