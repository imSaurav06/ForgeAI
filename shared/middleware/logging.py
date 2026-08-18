import time
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from shared.logging.logger import logger


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware to log HTTP request execution, status codes, and execution duration.
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        start_time = time.perf_counter()
        client_host = request.client.host if request.client else "unknown"

        logger.info(f"--> {request.method} {request.url.path} (Client: {client_host})")

        try:
            response = await call_next(request)
            duration_ms = (time.perf_counter() - start_time) * 1000
            response.headers["X-Process-Time-Ms"] = f"{duration_ms:.2f}"

            logger.info(
                f"<-- {request.method} {request.url.path} Status: {response.status_code} Duration: {duration_ms:.2f}ms"
            )
            return response
        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                f"<-- {request.method} {request.url.path} FAILED after {duration_ms:.2f}ms - Exception: {exc}"
            )
            raise
