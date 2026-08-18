import sys
from contextvars import ContextVar
from typing import Any

from loguru import logger

# ContextVars for tracing request, trace, and span IDs across async execution frames
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")
trace_id_ctx: ContextVar[str] = ContextVar("trace_id", default="-")
span_id_ctx: ContextVar[str] = ContextVar("span_id", default="-")


def get_request_id() -> str:
    """Retrieve current async context request ID."""
    return request_id_ctx.get()


def set_request_id(request_id: str) -> None:
    """Set request ID for current context."""
    request_id_ctx.set(request_id)


def get_trace_id() -> str:
    """Retrieve current async context trace ID."""
    return trace_id_ctx.get()


def set_trace_id(trace_id: str) -> None:
    """Set trace ID for current context."""
    trace_id_ctx.set(trace_id)


def get_span_id() -> str:
    """Retrieve current async context span ID."""
    return span_id_ctx.get()


def set_span_id(span_id: str) -> None:
    """Set span ID for current context."""
    span_id_ctx.set(span_id)


def log_formatter(record: dict[str, Any]) -> str:
    """
    Format log output with ISO timestamp, level, service name, request ID,
    trace ID, span ID, and log message.
    """
    req_id = get_request_id()
    trc_id = get_trace_id()
    spn_id = get_span_id()

    extra_req_id = record["extra"].get("request_id", req_id)
    service_name = record["extra"].get("service_name", "forge-ai")

    record["extra"]["request_id"] = extra_req_id
    record["extra"]["service_name"] = service_name
    record["extra"]["trace_id"] = trc_id
    record["extra"]["span_id"] = spn_id

    format_str = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{extra[service_name]}</cyan> | "
        "<magenta>req_id={extra[request_id]} trace_id={extra[trace_id]} span_id={extra[span_id]}</magenta> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>\n"
    )

    if record["exception"]:
        format_str += "{exception}\n"

    return format_str


def setup_logger(service_name: str = "forge-ai", log_level: str = "INFO") -> Any:
    """
    Configure and return a structured Loguru logger instance for a microservice.
    """
    logger.remove()  # Clear default handlers

    logger.add(
        sys.stdout,
        level=log_level.upper(),
        format=log_formatter,
        colorize=True,
        enqueue=True,
        backtrace=True,
        diagnose=True,
    )

    bound_logger = logger.bind(service_name=service_name, request_id="-")
    return bound_logger


__all__ = [
    "logger",
    "setup_logger",
    "get_request_id",
    "set_request_id",
    "get_trace_id",
    "set_trace_id",
    "get_span_id",
    "set_span_id",
    "request_id_ctx",
    "trace_id_ctx",
    "span_id_ctx",
]
