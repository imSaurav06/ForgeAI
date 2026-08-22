from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class RepoRegisterRequest(BaseModel):
    """Request payload for registering repository metadata."""

    name: str = Field(..., description="Repository name", json_schema_extra={"example": "Authentication Service"})
    path: str = Field(..., description="Local directory path", json_schema_extra={"example": "E:/Repos/auth"})
    git_remote: str | None = Field(default=None, description="Optional remote git URL")
    branch: str = Field(default="main", description="Git branch name")


class RepositoryMetadata(BaseModel):
    """Repository entity metadata model."""

    id: str = Field(..., description="Unique repository ID", json_schema_extra={"example": "repo_12345"})
    repository_id: str | None = Field(default=None, description="Unique repository ID alias")
    name: str = Field(..., description="Repository name")
    path: str = Field(..., description="Local directory path")
    git_remote: str | None = Field(default=None, description="Remote Git URL")
    branch: str = Field(default="main", description="Git branch")
    user_id: str | None = Field(default=None, description="Owner user ID")
    created_at: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="Registration timestamp",
    )
    indexed_at: str | None = Field(default=None, description="Last indexing timestamp")



class RepoOpenRequest(BaseModel):
    """Request payload to open local repository path."""

    path: str = Field(..., description="Absolute local directory path", json_schema_extra={"example": "E:/Repos/my-app"})


class RepoCloneRequest(BaseModel):
    """Request payload to clone remote repository."""

    url: str = Field(..., description="Git repository remote URL", json_schema_extra={"example": "https://github.com/org/repo.git"})
    destination_path: str | None = Field(default=None, description="Target local destination path")


class RepoIndexRequest(BaseModel):
    """Request payload to trigger symbol indexing."""

    force_reindex: bool = Field(default=False, description="Whether to clear existing index before scanning")


class SymbolItem(BaseModel):
    """AST Symbol definition model."""

    repository_id: str = Field(..., description="Parent repository ID")
    file: str = Field(..., description="Relative file path")
    symbol: str = Field(..., description="Symbol identifier name")
    type: str = Field(..., description="Symbol type: class, function, method, interface, enum, import, export, decorator")
    language: str = Field(..., description="Source code language")
    start_line: int = Field(..., description="Start line number")
    end_line: int = Field(..., description="End line number")
    signature: str = Field(..., description="Code signature snippet")
    parent_symbol: str | None = Field(default=None, description="Parent class/enclosing symbol if method")


class LanguageStatItem(BaseModel):
    """Language breakdown statistics item."""

    file_count: int = Field(..., description="Number of files in language")
    total_bytes: int = Field(..., description="Total size in bytes")
    percentage: float = Field(..., description="Percentage share of total repository size")


class DependencyEdge(BaseModel):
    """Dependency relationship edge."""

    source: str = Field(..., description="Source file relative path")
    target: str = Field(..., description="Target dependency file relative path")


class DependencyGraphResponse(BaseModel):
    """Dependency graph analysis response."""

    nodes: list[str] = Field(default_factory=list, description="Array of scanned source file paths")
    internal_edges: list[DependencyEdge] = Field(default_factory=list, description="Internal module dependency links")
    external_packages: list[str] = Field(default_factory=list, description="Third-party npm/pip package dependencies")
    circular_dependencies: list[list[str]] = Field(default_factory=list, description="Circular dependency chains detected")
    orphan_files: list[str] = Field(default_factory=list, description="Standalone files with zero internal dependencies")


class RepoScanResponse(BaseModel):
    """Repository scan result response."""

    repository_id: str = Field(..., description="Repository ID")
    total_files: int = Field(..., description="Total source files discovered")
    tree: list[dict[str, Any]] = Field(default_factory=list, description="Directory file tree hierarchy")
    languages: dict[str, LanguageStatItem] = Field(default_factory=dict, description="Language statistics breakdown")


class RepoIndexResponse(BaseModel):
    """Indexing execution response."""

    repository_id: str = Field(..., description="Repository ID")
    total_files: int = Field(..., description="Total indexed files count")
    total_symbols: int = Field(..., description="Total AST symbols extracted")
    indexed_at: str = Field(..., description="Completion timestamp")
    delta: dict[str, list[str]] = Field(default_factory=dict, description="Incremental diff: added, modified, deleted")


class DirectoryItem(BaseModel):
    """Local directory navigation item."""

    name: str = Field(..., description="Directory name")
    path: str = Field(..., description="Absolute canonical directory path")


class DriveItem(BaseModel):
    """Filesystem root drive item."""

    name: str = Field(..., description="Drive identifier or root name")
    path: str = Field(..., description="Root path")


class FilesystemBrowseResponse(BaseModel):
    """Filesystem directory navigation response."""

    path: str = Field(..., description="Current canonical directory path")
    parent: str | None = Field(default=None, description="Parent directory path if not at root")
    drives: list[DriveItem] = Field(default_factory=list, description="Available root drives on host")
    directories: list[DirectoryItem] = Field(default_factory=list, description="List of subdirectories in current path")

