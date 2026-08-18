"""
Shared Internal Service Authentication Middleware & Dependency.

Enforces HMAC-verified X-Internal-Service-Token header on all internal microservice endpoints,
blocking direct unauthenticated client bypass attempts while allowing public health endpoints.
"""

from __future__ import annotations

from typing import Any

from fastapi import Header, Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

from services.gateway.app.core.internal_auth import InternalAuthManager
from shared.exceptions.handlers import UnauthorizedException
from shared.logging.logger import logger

PUBLIC_PATHS = {"/health", "/docs", "/redoc", "/openapi.json"}


async def verify_internal_auth(
    x_internal_service_token: str | None = Header(default=None, alias="X-Internal-Service-Token"),
    x_user_id: str | None = Header(default=None, alias="X-User-ID"),
    x_user_role: str | None = Header(default=None, alias="X-User-Role"),
) -> dict[str, Any]:
    """FastAPI Header Dependency verifying internal service HMAC token."""
    manager = InternalAuthManager()
    if not manager.verify_internal_token(x_internal_service_token):
        raise UnauthorizedException(
            message="Direct access to internal microservice is prohibited. Missing or invalid X-Internal-Service-Token"
        )
    return {
        "token": x_internal_service_token,
        "user_id": x_user_id or "anonymous_internal",
        "user_role": x_user_role or "user",
    }


class InternalAuthMiddleware(BaseHTTPMiddleware):
    """Starlette/FastAPI Middleware enforcing internal authentication across all microservice routes."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        if path in PUBLIC_PATHS or any(path.startswith(p) for p in PUBLIC_PATHS):
            return await call_next(request)

        token = request.headers.get("X-Internal-Service-Token")
        manager = InternalAuthManager()
        if not manager.verify_internal_token(token):
            logger.warning(f"Rejected unauthenticated direct access attempt to internal route '{path}'")
            return JSONResponse(
                status_code=401,
                content={
                    "error": {
                        "code": "UNAUTHORIZED",
                        "message": "Direct access to internal microservice is prohibited. Missing or invalid X-Internal-Service-Token",
                        "status_code": 401,
                    }
                },
            )

        return await call_next(request)
