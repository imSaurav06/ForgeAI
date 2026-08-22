from fastapi import APIRouter, Query, status

from services.git.app.schemas.git_schemas import (
    GitActionResponse,
    GitBranchCreateRequest,
    GitCheckoutRequest,
    GitCommitItem,
    GitCommitRequest,
    GitDiffResponse,
    GitPushRequest,
    GitRemoteItem,
    GitRestoreRequest,
    GitStageRequest,
    GitStatusResponse,
    GitUnstageRequest,
)
from services.git.app.services.git_service import GitService
from shared.schemas.responses import SuccessResponse

router = APIRouter(prefix="/v1/git", tags=["Git Version Control"])
git_service = GitService()



@router.get(
    "/status",
    response_model=SuccessResponse[GitStatusResponse],
    summary="Get Git Repository Status",
    description="Returns current branch name, staged, modified, and untracked files.",
    responses={
        200: {"model": SuccessResponse[GitStatusResponse], "description": "Git status retrieved"},
    },
)
async def get_status(
    repo_id: str | None = Query(default=None),
    repository_id: str | None = Query(default=None),
) -> SuccessResponse[GitStatusResponse]:
    target_repo = repository_id or repo_id
    st = git_service.get_status(repository_id=target_repo)
    return SuccessResponse(data=GitStatusResponse(**st), message="Git status retrieved")


@router.get(
    "/diff",
    response_model=SuccessResponse[GitDiffResponse],
    summary="Get Git Unified Diff",
    description="Returns unified git diff text for working tree modifications.",
    responses={
        200: {"model": SuccessResponse[GitDiffResponse], "description": "Unified diff retrieved"},
    },
)
async def get_diff(
    repo_id: str | None = Query(default=None),
    repository_id: str | None = Query(default=None),
) -> SuccessResponse[GitDiffResponse]:
    target_repo = repository_id or repo_id
    diff = git_service.get_diff(repository_id=target_repo)
    return SuccessResponse(data=GitDiffResponse(**diff), message="Git diff retrieved")


@router.get(
    "/log",
    response_model=SuccessResponse[list[GitCommitItem]],
    summary="Get Git Commit History",
    description="Returns commit log history list with author, date, and commit message metadata.",
    responses={
        200: {"model": SuccessResponse[list[GitCommitItem]], "description": "Commit log retrieved"},
    },
)
async def get_log(
    limit: int = Query(default=10, ge=1, le=100),
    repo_id: str | None = Query(default=None),
    repository_id: str | None = Query(default=None),
) -> SuccessResponse[list[GitCommitItem]]:
    target_repo = repository_id or repo_id
    commits = git_service.get_log(limit=limit, repository_id=target_repo)
    items = [GitCommitItem(**c) for c in commits]
    return SuccessResponse(data=items, message="Git log retrieved")



@router.post(
    "/branches",
    response_model=SuccessResponse[GitActionResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create Git Branch",
    description="Creates a new git branch in target workspace repository.",
    responses={
        201: {"model": SuccessResponse[GitActionResponse], "description": "Branch created"},
    },
)
async def create_branch(payload: GitBranchCreateRequest) -> SuccessResponse[GitActionResponse]:
    res = git_service.create_branch(
        branch_name=payload.branch_name, checkout=payload.checkout, repository_id=payload.repository_id
    )
    return SuccessResponse(data=GitActionResponse(**res), message="Branch created successfully")


@router.post(
    "/checkout",
    response_model=SuccessResponse[GitActionResponse],
    summary="Checkout Git Branch or Commit",
    description="Checks out specified target branch or commit SHA.",
    responses={
        200: {"model": SuccessResponse[GitActionResponse], "description": "Checked out target"},
    },
)
async def checkout(payload: GitCheckoutRequest) -> SuccessResponse[GitActionResponse]:
    res = git_service.checkout(target=payload.target, repository_id=payload.repository_id)
    return SuccessResponse(data=GitActionResponse(**res), message="Checked out target successfully")


@router.post(
    "/commit",
    response_model=SuccessResponse[GitActionResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Stage & Create Git Commit",
    description="Stages specified or modified files and creates a new git commit.",
    responses={
        201: {"model": SuccessResponse[GitActionResponse], "description": "Commit created"},
    },
)
async def commit(payload: GitCommitRequest) -> SuccessResponse[GitActionResponse]:
    res = git_service.commit(
        message=payload.message, author=payload.author, files=payload.files, repository_id=payload.repository_id
    )
    return SuccessResponse(data=GitActionResponse(**res), message="Committed successfully")


@router.post(
    "/restore",
    response_model=SuccessResponse[GitActionResponse],
    summary="Restore Working Tree Files",
    description="Restores files or discards unstaged/staged workspace modifications.",
    responses={
        200: {"model": SuccessResponse[GitActionResponse], "description": "Files restored"},
    },
)
async def restore(payload: GitRestoreRequest) -> SuccessResponse[GitActionResponse]:
    res = git_service.restore(
        staged=payload.staged, files=payload.files, repository_id=payload.repository_id
    )
    return SuccessResponse(data=GitActionResponse(**res), message="Files restored successfully")


@router.post(
    "/stage",
    response_model=SuccessResponse[GitActionResponse],
    summary="Stage Working Tree Files",
    description="Stages specified files into the Git index (git add).",
    responses={
        200: {"model": SuccessResponse[GitActionResponse], "description": "Files staged successfully"},
    },
)
async def stage(payload: GitStageRequest) -> SuccessResponse[GitActionResponse]:
    res = git_service.stage(files=payload.files, repository_id=payload.repository_id)
    return SuccessResponse(data=GitActionResponse(**res), message="Files staged successfully")


@router.post(
    "/unstage",
    response_model=SuccessResponse[GitActionResponse],
    summary="Unstage Staged Files",
    description="Unstages specified files from the Git index (git restore --staged).",
    responses={
        200: {"model": SuccessResponse[GitActionResponse], "description": "Files unstaged successfully"},
    },
)
async def unstage(payload: GitUnstageRequest) -> SuccessResponse[GitActionResponse]:
    res = git_service.unstage(files=payload.files, repository_id=payload.repository_id)
    return SuccessResponse(data=GitActionResponse(**res), message="Files unstaged successfully")


@router.get(
    "/remotes",
    response_model=SuccessResponse[list[GitRemoteItem]],
    summary="Get Configured Git Remotes",
    description="Returns list of configured git remotes with name and URL.",
    responses={
        200: {"model": SuccessResponse[list[GitRemoteItem]], "description": "Remotes retrieved"},
    },
)
async def get_remotes(repository_id: str | None = Query(default=None, alias="repo_id")) -> SuccessResponse[list[GitRemoteItem]]:
    remotes = git_service.get_remotes(repository_id=repository_id)
    items = [GitRemoteItem(**r) for r in remotes]
    return SuccessResponse(data=items, message="Git remotes retrieved")


@router.post(
    "/push",
    response_model=SuccessResponse[GitActionResponse],
    summary="Push Git Branch to Remote",
    description="Pushes local git branch to specified remote repository.",
    responses={
        200: {"model": SuccessResponse[GitActionResponse], "description": "Branch pushed"},
    },
)
async def push(payload: GitPushRequest) -> SuccessResponse[GitActionResponse]:
    res = git_service.push(
        branch_name=payload.branch_name,
        remote=payload.remote,
        set_upstream=payload.set_upstream,
        repository_id=payload.repository_id,
    )
    return SuccessResponse(data=GitActionResponse(**res), message=res.get("message", "Git push executed"))

