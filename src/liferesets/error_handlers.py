"""Consistent, redacted HTTP error responses for the API."""

import logging
from typing import Any

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


def _error_response(
    status_code: int,
    code: str,
    message: str,
    *,
    headers: dict[str, str] | None = None,
    issues: list[dict[str, Any]] | None = None,
) -> JSONResponse:
    error: dict[str, Any] = {"code": code, "message": message}
    if issues is not None:
        error["issues"] = issues
    return JSONResponse(
        status_code=status_code,
        content={"error": error},
        headers=headers,
    )


async def handle_http_exception(
    _request: Request, exception: StarletteHTTPException
) -> JSONResponse:
    """Return expected HTTP failures in the common error envelope."""
    detail = exception.detail
    if isinstance(detail, dict) and isinstance(detail.get("code"), str):
        code = detail["code"]
        message = detail.get("message", "The request could not be completed.")
    else:
        code = "http_error"
        message = str(detail)

    return _error_response(
        exception.status_code,
        code,
        message,
        headers=exception.headers,
    )


async def handle_validation_exception(
    _request: Request, exception: RequestValidationError
) -> JSONResponse:
    """Return validation locations without echoing submitted values."""
    issues = [
        {
            "location": [str(part) for part in error["loc"]],
            "code": error["type"],
        }
        for error in exception.errors()
    ]
    return _error_response(
        422,
        "validation_error",
        "Request validation failed.",
        issues=issues,
    )


async def handle_unexpected_exception(
    request: Request, exception: Exception
) -> JSONResponse:
    """Log only non-sensitive context and return a generic server error."""
    logger.error(
        "Unhandled application error type=%s method=%s",
        type(exception).__name__,
        request.method,
    )
    return _error_response(
        500,
        "internal_error",
        "An unexpected error occurred.",
    )


def register_error_handlers(app: FastAPI) -> None:
    """Install the standard HTTP, validation, and unexpected error handlers."""
    app.add_exception_handler(StarletteHTTPException, handle_http_exception)
    app.add_exception_handler(RequestValidationError, handle_validation_exception)
    app.add_exception_handler(Exception, handle_unexpected_exception)
