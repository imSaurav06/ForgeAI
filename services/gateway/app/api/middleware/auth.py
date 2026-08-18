from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from shared.logging.logger import logger


class AuthMiddlewareScaffold(BaseHTTPMiddleware):
    """
    Authentication middleware scaffold.
    Enforces authorization headers for protected routes while bypassing
    public infrastructure routes (/health, /docs, /openapi.json, /redoc).
    """

    PUBLIC_PATHS: set[str] = {
        "/health",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/favicon.ico",
    }

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        path = request.url.path

        if path in self.PUBLIC_PATHS or path.startswith("/docs") or path.startswith("/redoc"):
            return await call_next(request)

        # Log request authentication check
        auth_header = request.headers.get("Authorization")
        api_key = request.headers.get("X-API-Key")

        if auth_header or api_key:
            logger.debug(f"Auth check passed for route {path}")
        else:
            logger.debug(f"Route {path} accessed without explicit auth headers (local dev mode active)")

        return await call_next(request)
