from __future__ import annotations

from pydantic import BaseModel, Field


class ReadFileRequest(BaseModel):
    """Payload to read file content from a selected repository."""

    path: str = Field(
        ...,
        min_length=1,
        description="Relative file path inside the selected repository",
        json_schema_extra={"example": "shared/config/settings.py"},
    )
    start_line: int | None = Field(
        default=None,
        ge=1,
        description="Optional 1-based start line",
    )
    end_line: int | None = Field(
        default=None,
        ge=1,
        description="Optional inclusive end line",
    )
    repository_id: str = Field(
        ...,
        min_length=1,
        description="Target repository ID",
    )


class ReadFileResponse(BaseModel):
    """File read output response."""

    path: str = Field(..., description="Relative file path")
    content: str = Field(..., description="File text content")
    total_lines: int = Field(..., ge=0, description="Total line count")


class WriteFileRequest(BaseModel):
    """Payload to write file content into a selected repository."""

    path: str = Field(
        ...,
        min_length=1,
        description="Relative file path inside the selected repository",
        json_schema_extra={"example": "tmp_script.py"},
    )
    content: str = Field(
        ...,
        description="Text content to write",
    )
    repository_id: str = Field(
        ...,
        min_length=1,
        description="Target repository ID",
    )


class SearchFilesRequest(BaseModel):
    """Payload to search files inside a selected repository."""

    pattern: str = Field(
        ...,
        min_length=1,
        description="Case-insensitive text pattern to search for",
        json_schema_extra={"example": "validate_jwt"},
    )
    path: str | None = Field(
        default=None,
        description="Optional relative directory inside the selected repository",
    )
    repository_id: str = Field(
        ...,
        min_length=1,
        description="Target repository ID",
    )


class ApplyPatchRequest(BaseModel):
    """Payload to execute an atomic multi-file patch in a repository."""

    repository_id: str = Field(
        ...,
        min_length=1,
        description="Target repository ID",
    )
    files_to_create: list[dict[str, str]] | None = Field(
        default=None,
        description="Files to create",
    )
    files_to_modify: list[dict[str, str]] | None = Field(
        default=None,
        description="Files to modify",
    )
    files_to_delete: list[str] | None = Field(
        default=None,
        description="Relative file paths to delete",
    )


class DeleteFileRequest(BaseModel):
    """Payload to delete a file from the selected repository."""

    repository_id: str = Field(
        ...,
        min_length=1,
        description="Target repository ID",
    )
    path: str = Field(
        ...,
        min_length=1,
        description="Relative file path to delete",
    )


class RunCommandRequest(BaseModel):
    """Payload to execute a one-shot command in a selected repository."""

    repository_id: str = Field(
        ...,
        min_length=1,
        description="Target repository ID",
    )
    command: str = Field(
        ...,
        min_length=1,
        max_length=32 * 1024,
        description="Terminal command to execute",
        json_schema_extra={"example": "python -m pytest"},
    )
    cwd: str | None = Field(
        default=None,
        description="Optional relative working directory inside the selected repository",
    )
    timeout_sec: float = Field(
        default=30.0,
        gt=0,
        description="Execution timeout limit in seconds",
    )


class TerminalSessionRequest(BaseModel):
    """Payload to create or reuse a persistent terminal bound to a repository."""

    session_id: str = Field(
        ...,
        min_length=1,
        max_length=256,
        description="Persistent terminal session ID",
    )
    repository_id: str = Field(
        ...,
        min_length=1,
        description="Repository ID owning the terminal session",
    )
    workspace: str | None = Field(
        default=None,
        description="Optional relative workspace directory inside the selected repository",
    )
    shell: str | None = Field(
        default=None,
        description="Optional shell executable",
    )
    cols: int = Field(
        default=120,
        ge=1,
        le=500,
        description="Terminal column count",
    )
    rows: int = Field(
        default=30,
        ge=1,
        le=500,
        description="Terminal row count",
    )


class TerminalInputRequest(BaseModel):
    """Payload to write input into an existing persistent terminal."""

    session_id: str = Field(
        ...,
        min_length=1,
        max_length=256,
        description="Persistent terminal session ID",
    )
    data: str = Field(
        ...,
        max_length=32 * 1024,
        description="Terminal input data",
    )


class TerminalInterruptRequest(BaseModel):
    """Payload to interrupt an existing persistent terminal."""

    session_id: str = Field(
        ...,
        min_length=1,
        max_length=256,
        description="Persistent terminal session ID",
    )


class TerminalExecuteRequest(BaseModel):
    """Payload to execute a command inside an existing persistent PTY session."""

    session_id: str = Field(
        ...,
        min_length=1,
        max_length=256,
        description="Persistent terminal session ID",
    )
    command: str = Field(
        ...,
        min_length=1,
        max_length=32 * 1024,
        description="Command to execute inside the persistent PTY",
        json_schema_extra={"example": "python -m pytest"},
    )
    timeout_sec: float = Field(
        default=300.0,
        gt=0,
        description="Maximum command execution time in seconds",
    )


class RunTestRequest(BaseModel):
    """Payload to run pytest inside a selected repository."""

    repository_id: str = Field(
        ...,
        min_length=1,
        description="Target repository ID",
    )
    test_path: str | None = Field(
        default=None,
        description="Optional relative test file or directory inside the repository",
    )
    timeout_sec: float = Field(
        default=60.0,
        gt=0,
        description="Timeout limit",
    )


class RunQualityToolRequest(BaseModel):
    """Payload to run build, linter, or formatter in a selected repository."""

    repository_id: str = Field(
        ...,
        min_length=1,
        description="Target repository ID",
    )
    target_path: str | None = Field(
        default=None,
        description="Optional relative target file or directory inside the repository",
    )
    command: str | None = Field(
        default=None,
        min_length=1,
        max_length=32 * 1024,
        description="Optional build command override",
    )