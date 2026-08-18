from typing import Any

from pydantic import BaseModel, Field


class OpenRepoRequest(BaseModel):
    """Request payload to open a local repository directory."""

    path: str = Field(..., description="Absolute local directory path", json_schema_extra={"example": "E:/Repos/my-app"})


class CloneRepoRequest(BaseModel):
    """Request payload to clone a remote git repository."""

    url: str = Field(..., description="Git repository remote URL", json_schema_extra={"example": "https://github.com/org/repo.git"})
    destination_path: str | None = Field(default=None, description="Optional target directory")


class IndexRepoRequest(BaseModel):
    """Request payload to initiate vector indexing on a repository."""

    force_reindex: bool = Field(default=False, description="Whether to clear existing index before parsing")


class RepoTreeNode(BaseModel):
    """File tree node model."""

    name: str = Field(..., description="File or directory name")
    path: str = Field(..., description="Relative file path")
    type: str = Field(..., description="Node type: 'file' or 'directory'")
    children: list["RepoTreeNode"] | None = Field(default=None, description="Sub-nodes if directory")


class RepoStatusResponse(BaseModel):
    """Repository parsing & indexing status."""

    repository_id: str = Field(..., description="Repository ID")
    path: str = Field(..., description="Local repo path")
    total_files: int = Field(default=0, description="Total source files discovered")
    indexed_files: int = Field(default=0, description="Total indexed files")
    status: str = Field(default="idle", description="Indexing status: idle, indexing, completed, failed")
    languages: list[str] = Field(default_factory=list, description="Detected programming languages")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional repo metadata")


class FileWriteRequest(BaseModel):
    """Payload to create or update a file."""

    path: str = Field(..., description="Relative file path")
    content: str = Field(default="", description="Text content to write")


class DirectoryItem(BaseModel):
    """Directory item for navigation."""

    name: str = Field(..., description="Directory name")
    path: str = Field(..., description="Directory absolute path")


class DriveItem(BaseModel):
    """Host filesystem drive or root."""

    name: str = Field(..., description="Drive identifier or root name")
    path: str = Field(..., description="Root path")


class FilesystemBrowseResponse(BaseModel):
    """Directory browsing response."""

    path: str = Field(..., description="Current canonical directory path")
    parent: str | None = Field(default=None, description="Parent directory path")
    drives: list[DriveItem] = Field(default_factory=list, description="Available root drives")
    directories: list[DirectoryItem] = Field(default_factory=list, description="Subdirectories in path")

