from datetime import UTC, datetime

from pydantic import BaseModel, Field


class ProjectCreateRequest(BaseModel):
    """Request payload for creating a new project workspace."""

    name: str = Field(..., description="Project workspace name", json_schema_extra={"example": "Authentication Engine"})
    path: str = Field(..., description="Local file system path", json_schema_extra={"example": "/path/to/repo"})
    description: str | None = Field(default=None, description="Project summary description")


class ProjectResponse(BaseModel):
    """Project entity model."""

    id: str = Field(..., description="Unique project ID", json_schema_extra={"example": "proj_12345"})
    name: str = Field(..., description="Project workspace name")
    path: str = Field(..., description="Local repository directory path")
    description: str | None = Field(default=None, description="Project description")
    created_at: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="Project creation timestamp",
    )
    is_indexed: bool = Field(default=False, description="Repository vector index status")


class ProjectListResponse(BaseModel):
    """List of registered projects."""

    projects: list[ProjectResponse] = Field(default_factory=list)
    total: int = Field(default=0, description="Total projects count")
