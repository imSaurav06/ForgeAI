import time
from collections import defaultdict
from collections.abc import Awaitable, Callable

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from shared.logging.logger import get_request_id, get_trace_id, logger
from shared.schemas.responses import ErrorDetails, ErrorResponse


class RateLimiter:
    """In-memory sliding window rate limiter per client key."""

    def __init__(self, requests_per_minute: int = 120, window_seconds: int = 60) -> None:
        self.requests_per_minute = requests_per_minute
        self.window_seconds = window_seconds
        self.history: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, client_key: str) -> tuple[bool, int]:
        """
        Check if request is allowed for key.
        Returns (is_allowed, seconds_until_reset).
        """
        now = time.time()
        cutoff = now - self.window_seconds

        # Prune old timestamps
        self.history[client_key] = [t for t in self.history[client_key] if t > cutoff]

        if len(self.history[client_key]) >= self.requests_per_minute:
            oldest = self.history[client_key][0]
            retry_after = int(self.window_seconds - (now - oldest)) + 1
            return False, max(retry_after, 1)

        self.history[client_key].append(now)
        return True, 0


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware enforcing sliding-window rate limits per client IP or user ID."""

    EXEMPT_PATHS: set[str] = {"/health", "/metrics", "/docs", "/redoc", "/openapi.json"}

    def __init__(self, app, requests_per_minute: int = 120) -> None:
        super().__init__(app)
        self.limiter = RateLimiter(requests_per_minute=requests_per_minute)

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        path = request.url.path
        if path in self.EXEMPT_PATHS or path.startswith("/docs") or path.startswith("/redoc"):
            return await call_next(request)

        # Identify client key: user ID if authenticated, else IP address
        user_id = request.headers.get("X-User-ID")
        client_key = user_id if user_id else (request.client.host if request.client else "unknown_client")

        allowed, retry_after = self.limiter.is_allowed(client_key)
        if not allowed:
            req_id = get_request_id()
            trc_id = get_trace_id()
            logger.warning(f"Rate limit exceeded for key '{client_key}' on path '{path}'")

            error_resp = ErrorResponse(
                code="RATE_LIMIT_EXCEEDED",
                message=f"Rate limit exceeded. Try again in {retry_after} seconds.",
                service="api-gateway",
                request_id=req_id,
                trace_id=trc_id,
                error=ErrorDetails(
                    code="RATE_LIMIT_EXCEEDED",
                    details={"retry_after_seconds": retry_after, "limit_per_minute": self.limiter.requests_per_minute},
                ),
            )
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content=error_resp.model_dump(),
                headers={"Retry-After": str(retry_after)},
            )

        return await call_next(request)
