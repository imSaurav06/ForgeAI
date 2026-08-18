from pydantic import BaseModel, Field


class GitStatusResponse(BaseModel):
    """Git repository working tree status with dual-compatible field aliases."""

    branch: str = Field(..., description="Current checked out branch name")
    clean: bool = Field(..., description="True if working tree is clean")
    staged: list[str] = Field(default_factory=list, description="Staged files list")
    unstaged: list[str] = Field(default_factory=list, description="Unstaged modified files")
    untracked: list[str] = Field(default_factory=list, description="Untracked files list")
    staged_files: list[str] = Field(default_factory=list, description="Staged files list alias")
    modified_files: list[str] = Field(default_factory=list, description="Modified unstaged files alias")
    untracked_files: list[str] = Field(default_factory=list, description="Untracked files alias")


class GitDiffResponse(BaseModel):
    """Unified git diff output with dual-compatible field aliases."""

    diff: str = Field(default="", description="Unified diff text content")
    diff_text: str = Field(default="", description="Unified diff text content alias")
    files_changed: int = Field(default=0, description="Total count of changed files")
    files_changed_count: int = Field(default=0, description="Total count of changed files alias")


class GitCommitLog(BaseModel):
    """Git commit metadata entry."""

    hash: str = Field(..., description="Commit SHA-1 hash")
    author: str = Field(..., description="Commit author name & email")
    date: str = Field(..., description="Commit date timestamp")
    message: str = Field(..., description="Commit message subject line")


GitCommitItem = GitCommitLog


class GitLogResponse(BaseModel):
    """List of recent git commit entries."""

    commits: list[GitCommitLog] = Field(default_factory=list)


class GitCreateBranchRequest(BaseModel):
    """Request payload to create a new git branch."""

    branch_name: str = Field(..., description="New branch name", json_schema_extra={"example": "feature/auth-rate-limit"})
    checkout: bool = Field(default=True, description="Whether to checkout the branch immediately")
    repository_id: str | None = Field(default=None, description="Optional target repository ID")


GitBranchCreateRequest = GitCreateBranchRequest


class GitCheckoutRequest(BaseModel):
    """Request payload to checkout an existing branch or commit SHA."""

    target: str = Field(..., description="Branch name or commit hash to checkout", json_schema_extra={"example": "main"})
    repository_id: str | None = Field(default=None, description="Optional target repository ID")


class GitCommitRequest(BaseModel):
    """Request payload to create a git commit."""

    message: str = Field(..., description="Commit message description", json_schema_extra={"example": "feat(auth): add JWT authentication"})
    files: list[str] | None = Field(default=None, description="Optional specific files to stage and commit")
    repository_id: str | None = Field(default=None, description="Optional target repository ID")


class GitRestoreRequest(BaseModel):
    """Request payload to restore or discard local changes."""

    files: list[str] = Field(..., description="Files to discard/restore to HEAD")
    staged: bool = Field(default=False, description="Whether to unstage staged files")
    repository_id: str | None = Field(default=None, description="Optional target repository ID")


class GitStageRequest(BaseModel):
    """Request payload to stage specific files."""

    files: list[str] = Field(..., description="Target files to stage (git add)")
    repository_id: str | None = Field(default=None, description="Optional target repository ID")


class GitUnstageRequest(BaseModel):
    """Request payload to unstage specific files."""

    files: list[str] = Field(..., description="Target files to unstage (git restore --staged)")
    repository_id: str | None = Field(default=None, description="Optional target repository ID")


class GitActionResponse(BaseModel):
    """Generic action response for branch/commit/restore operations."""

    status: str = Field(default="success", description="Action status string")
    success: bool = Field(default=True, description="Success flag")
    message: str = Field(default="Git action completed successfully")
