from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


class ServiceHealthItem(BaseModel):
    """Health item for an individual microservice."""

    service_name: str = Field(..., description="Service identifier")
    status: Literal["healthy", "degraded", "unhealthy", "offline"] = Field(..., description="Service status")
    version: str | None = Field(default=None, description="Microservice reported version")
    url: str = Field(..., description="Microservice base URL")
    latency_ms: float | None = Field(default=None, description="Health check ping latency in milliseconds")
    error: str | None = Field(default=None, description="Error detail if service is unhealthy or offline")


class SystemHealthResponse(BaseModel):
    """Aggregated health status response covering all 8 backend microservices."""

    status: Literal["healthy", "degraded", "unhealthy"] = Field(..., description="Overall system health status")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="Health check aggregation timestamp",
    )
    services: dict[str, ServiceHealthItem] = Field(
        ..., description="Map of service name to health status item"
    )
