from datetime import UTC, datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class BaseResponse(BaseModel):
    """Base response model with common metadata."""

    success: bool = Field(..., description="Operation success status")
    request_id: str = Field(default="-", description="Correlation ID for request tracing")
    trace_id: str = Field(default="-", description="Distributed trace ID")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="ISO 8601 UTC timestamp",
    )


class SuccessResponse(BaseResponse, Generic[T]):
    """Standardized success response wrapper."""

    success: bool = Field(default=True, description="True for successful requests")
    message: str = Field(default="Operation completed successfully", description="Response message")
    data: T | None = Field(default=None, description="Payload data")


class ErrorDetails(BaseModel):
    """Detailed error info structure."""

    code: str = Field(..., description="Machine-readable error code")
    details: Any | None = Field(default=None, description="Additional context or validation errors")


class ErrorResponse(BaseResponse):
    """Unified error response wrapper conforming to production contract."""

    success: bool = Field(default=False, description="False for failed requests")
    code: str = Field(default="INTERNAL_ERROR", description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error description")
    service: str = Field(default="api-gateway", description="Originating service name")
    error: ErrorDetails = Field(..., description="Structured error details")


class HealthResponse(BaseModel):
    """Health check status model exposed by GET /health endpoints."""

    service: str = Field(..., description="Microservice name")
    status: str = Field(default="healthy", description="Health status (healthy, degraded, unhealthy)")
    version: str = Field(..., description="Microservice semantic version")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="Health check execution timestamp",
    )
    details: dict[str, Any] | None = Field(
        default=None, description="Optional component health details"
    )


class PaginationMeta(BaseModel):
    """Pagination metadata model."""

    page: int = Field(..., ge=1, description="Current page number")
    page_size: int = Field(..., ge=1, description="Items per page")
    total_items: int = Field(..., ge=0, description="Total record count")
    total_pages: int = Field(..., ge=0, description="Total available pages")


class PaginatedResponse(BaseResponse, Generic[T]):
    """Standardized paginated list response wrapper."""

    success: bool = Field(default=True, description="True for successful requests")
    data: list[T] = Field(default_factory=list, description="Page items array")
    pagination: PaginationMeta = Field(..., description="Pagination metadata")
