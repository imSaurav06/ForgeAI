from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from shared.logging.logger import get_request_id, get_trace_id, logger
from shared.schemas.responses import ErrorDetails, ErrorResponse


class ForgeException(Exception):
    """Base domain exception for ForgeAI platform."""

    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_ERROR",
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details


class NotFoundException(ForgeException):
    """Resource not found exception (404)."""

    def __init__(self, message: str = "Requested resource not found", details: Any | None = None) -> None:
        super().__init__(
            message=message,
            code="NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
            details=details,
        )


class ValidationException(ForgeException):
    """Business logic validation failure (422/400)."""

    def __init__(self, message: str = "Validation failed", details: Any | None = None) -> None:
        super().__init__(
            message=message,
            code="VALIDATION_ERROR",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details,
        )


class ServiceUnavailableException(ForgeException):
    """Downstream microservice or dependency unavailable (503)."""

    def __init__(self, message: str = "Service temporarily unavailable", details: Any | None = None) -> None:
        super().__init__(
            message=message,
            code="SERVICE_UNAVAILABLE",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            details=details,
        )


class UnauthorizedException(ForgeException):
    """Authentication failure (401)."""

    def __init__(self, message: str = "Unauthorized access", details: Any | None = None) -> None:
        super().__init__(
            message=message,
            code="UNAUTHORIZED",
            status_code=status.HTTP_401_UNAUTHORIZED,
            details=details,
        )


class ForbiddenException(ForgeException):
    """Permission or resource authorization failure (403)."""

    def __init__(self, message: str = "Access forbidden", details: Any | None = None) -> None:
        super().__init__(
            message=message,
            code="FORBIDDEN",
            status_code=status.HTTP_403_FORBIDDEN,
            details=details,
        )


def register_exception_handlers(app: FastAPI) -> None:
    """Register unified exception handlers on a FastAPI application."""

    service_name = getattr(app, "title", "forge-service")

    @app.exception_handler(ForgeException)
    async def forge_exception_handler(request: Request, exc: ForgeException) -> JSONResponse:
        req_id = get_request_id()
        trc_id = get_trace_id()
        logger.warning(f"ForgeException [{exc.code}] {exc.message} - Path: {request.url.path}")
        error_resp = ErrorResponse(
            code=exc.code,
            message=exc.message,
            service=service_name,
            request_id=req_id,
            trace_id=trc_id,
            error=ErrorDetails(code=exc.code, details=exc.details),
        )
        return JSONResponse(status_code=exc.status_code, content=error_resp.model_dump())

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        req_id = get_request_id()
        trc_id = get_trace_id()
        logger.warning(f"RequestValidationError - Path: {request.url.path} - Errors: {exc.errors()}")
        error_resp = ErrorResponse(
            code="VALIDATION_ERROR",
            message="Request validation failed",
            service=service_name,
            request_id=req_id,
            trace_id=trc_id,
            error=ErrorDetails(code="VALIDATION_ERROR", details=exc.errors()),
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=error_resp.model_dump(),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        req_id = get_request_id()
        trc_id = get_trace_id()
        logger.warning(f"HTTPException [{exc.status_code}] - Path: {request.url.path} - Detail: {exc.detail}")
        error_resp = ErrorResponse(
            code=f"HTTP_{exc.status_code}",
            message=str(exc.detail),
            service=service_name,
            request_id=req_id,
            trace_id=trc_id,
            error=ErrorDetails(code=f"HTTP_{exc.status_code}", details=None),
        )
        return JSONResponse(status_code=exc.status_code, content=error_resp.model_dump())

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        req_id = get_request_id()
        trc_id = get_trace_id()
        logger.exception(f"Unhandled internal exception on {request.method} {request.url.path}: {exc}")
        error_resp = ErrorResponse(
            code="INTERNAL_SERVER_ERROR",
            message="An unexpected internal server error occurred",
            service=service_name,
            request_id=req_id,
            trace_id=trc_id,
            error=ErrorDetails(code="INTERNAL_SERVER_ERROR", details=str(exc) if app.debug else None),
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_resp.model_dump(),
        )
