from pydantic import BaseModel, Field


class GitStatusResponse(BaseModel):
    """Git repository status model with dual-compatible field aliases."""

    branch: str = Field(..., description="Current git branch name")
    clean: bool = Field(..., description="Whether working tree is clean")
    staged: list[str] = Field(default_factory=list, description="Staged files list")
    unstaged: list[str] = Field(default_factory=list, description="Unstaged modified files list")
    untracked: list[str] = Field(default_factory=list, description="Untracked files list")
    staged_files: list[str] = Field(default_factory=list, description="Staged files list alias")
    modified_files: list[str] = Field(default_factory=list, description="Modified unstaged files list alias")
    untracked_files: list[str] = Field(default_factory=list, description="Untracked files list alias")


class GitDiffResponse(BaseModel):
    """Git unified diff response model with dual-compatible field aliases."""

    diff: str = Field(default="", description="Unified git diff string")
    diff_text: str = Field(default="", description="Unified git diff string alias")
    files_changed: int = Field(default=0, description="Total files changed count")
    files_changed_count: int = Field(default=0, description="Total files changed count alias")


class GitCommitItem(BaseModel):
    """Git commit metadata item."""

    hash: str = Field(..., description="Commit hash SHA")
    author: str = Field(..., description="Commit author")
    date: str = Field(..., description="Commit date timestamp")
    message: str = Field(..., description="Commit message")


class GitBranchCreateRequest(BaseModel):
    """Payload to create a new branch."""

    branch_name: str = Field(..., description="New branch name", json_schema_extra={"example": "feature/jwt-auth"})
    checkout: bool = Field(default=True, description="Whether to checkout branch immediately")
    repository_id: str | None = Field(default=None, description="Optional target repository ID")


class GitCheckoutRequest(BaseModel):
    """Payload to checkout existing branch or commit."""

    target: str = Field(..., description="Branch name or commit hash to checkout", json_schema_extra={"example": "main"})
    repository_id: str | None = Field(default=None, description="Optional target repository ID")


class GitCommitRequest(BaseModel):
    """Payload to stage files and create a commit."""

    message: str = Field(..., description="Commit message", json_schema_extra={"example": "feat: add JWT authentication middleware"})
    author: str | None = Field(default=None, description="Commit author string")
    files: list[str] | None = Field(default=None, description="Specific files to stage; if empty, stage all")
    repository_id: str | None = Field(default=None, description="Optional target repository ID")


class GitRestoreRequest(BaseModel):
    """Payload to discard working tree changes or restore files."""

    staged: bool = Field(default=False, description="Unstage files")
    files: list[str] | None = Field(default=None, description="Target files to restore; if empty, restore all")
    repository_id: str | None = Field(default=None, description="Optional target repository ID")


class GitStageRequest(BaseModel):
    """Payload to stage specific files."""

    files: list[str] = Field(..., description="Target files to stage (git add)")
    repository_id: str | None = Field(default=None, description="Optional target repository ID")


class GitUnstageRequest(BaseModel):
    """Payload to unstage specific files."""

    files: list[str] = Field(..., description="Target files to unstage (git restore --staged)")
    repository_id: str | None = Field(default=None, description="Optional target repository ID")


class GitRemoteItem(BaseModel):
    """Git remote configuration item."""

    name: str = Field(..., description="Remote name (e.g., origin)")
    url: str = Field(..., description="Remote repository URL")
    type: str = Field(default="", description="Remote type (fetch or push)")


class GitPushRequest(BaseModel):
    """Payload to push branch to remote repository."""

    branch_name: str | None = Field(default=None, description="Optional branch name to push")
    remote: str = Field(default="origin", description="Target remote name")
    set_upstream: bool = Field(default=True, description="Whether to set upstream branch tracking")
    repository_id: str | None = Field(default=None, description="Optional target repository ID")


class GitActionResponse(BaseModel):
    """Generic Git action status response model."""

    status: str = Field(default="success", description="Action status")
    success: bool = Field(default=True, description="Success flag")
    message: str = Field(..., description="Details message")
    commit_hash: str | None = Field(default=None, description="Created commit hash if applicable")
    branch_name: str | None = Field(default=None, description="Created branch name if applicable")
    branch: str | None = Field(default=None, description="Pushed branch name if applicable")
    remote: str | None = Field(default=None, description="Target remote name if applicable")
    exit_code: int | None = Field(default=None, description="Subprocess exit code if applicable")
    stdout: str | None = Field(default=None, description="Command stdout")
    stderr: str | None = Field(default=None, description="Command stderr")

