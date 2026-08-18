import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from shared.logging.logger import (
    set_request_id,
    set_span_id,
    set_trace_id,
)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware that generates and propagates distributed tracing headers:
    X-Request-ID, X-Trace-ID, and X-Span-ID.
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        trace_id = request.headers.get("X-Trace-ID") or str(uuid.uuid4())
        span_id = str(uuid.uuid4())[:8]

        set_request_id(request_id)
        set_trace_id(trace_id)
        set_span_id(span_id)

        request.state.request_id = request_id
        request.state.trace_id = trace_id
        request.state.span_id = span_id

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Trace-ID"] = trace_id
        response.headers["X-Span-ID"] = span_id
        return response
