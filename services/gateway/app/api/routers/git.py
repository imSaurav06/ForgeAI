from fastapi import APIRouter, Depends, Query, Request, Response

from services.gateway.app.api.dependencies.auth import verify_auth_token
from services.gateway.app.api.dependencies.proxy import get_proxy_service
from services.gateway.app.schemas.git import (
    GitActionResponse,
    GitBranchCreateRequest,
    GitCheckoutRequest,
    GitCommitItem,
    GitCommitRequest,
    GitDiffResponse,
    GitLogResponse,
    GitRestoreRequest,
    GitStageRequest,
    GitStatusResponse,
    GitUnstageRequest,
)
from services.gateway.app.services.proxy_service import GatewayProxyService
from shared.schemas.responses import ErrorResponse, SuccessResponse

router = APIRouter(prefix="/git", tags=["Git Version Control"])


@router.get(
    "/status",
    response_model=SuccessResponse[GitStatusResponse],
    summary="Get Git Repository Status",
    description="Returns current branch, staged, modified, and untracked files.",
    responses={
        200: {"model": SuccessResponse[GitStatusResponse], "description": "Git status retrieved"},
        503: {"model": ErrorResponse, "description": "Git Service unavailable"},
    },
)
async def get_status(
    request: Request,
    repo_id: str | None = Query(default=None, alias="repository_id"),
    auth: dict = Depends(verify_auth_token),
    proxy: GatewayProxyService = Depends(get_proxy_service),
) -> Response:
    return await proxy.proxy_to_service("git", "/v1/git/status", request)


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
    request: Request,
    repo_id: str | None = Query(default=None, alias="repository_id"),
    auth: dict = Depends(verify_auth_token),
    proxy: GatewayProxyService = Depends(get_proxy_service),
) -> Response:
    return await proxy.proxy_to_service("git", "/v1/git/diff", request)


@router.get(
    "/log",
    response_model=SuccessResponse[GitLogResponse],
    summary="Get Git Commit History Log",
    description="Returns recent commit history objects.",
    responses={
        200: {"model": SuccessResponse[GitLogResponse], "description": "Git log retrieved"},
    },
)
async def get_log(
    request: Request,
    repo_id: str | None = Query(default=None, alias="repository_id"),
    auth: dict = Depends(verify_auth_token),
    proxy: GatewayProxyService = Depends(get_proxy_service),
) -> Response:
    return await proxy.proxy_to_service("git", "/v1/git/log", request)


@router.post(
    "/branches",
    response_model=SuccessResponse[GitActionResponse],
    summary="Create Git Branch",
    description="Creates a new local git branch in workspace.",
    responses={
        200: {"model": SuccessResponse[GitActionResponse], "description": "Branch created"},
    },
)
async def create_branch(
    payload: GitBranchCreateRequest,
    request: Request,
    auth: dict = Depends(verify_auth_token),
    proxy: GatewayProxyService = Depends(get_proxy_service),
) -> Response:
    return await proxy.proxy_to_service("git", "/v1/git/branches", request, json_body=payload.model_dump())


@router.post(
    "/checkout",
    response_model=SuccessResponse[GitActionResponse],
    summary="Checkout Git Branch or Commit",
    description="Checks out specified target branch or commit SHA.",
    responses={
        200: {"model": SuccessResponse[GitActionResponse], "description": "Target checked out"},
    },
)
async def checkout_target(
    payload: GitCheckoutRequest,
    request: Request,
    auth: dict = Depends(verify_auth_token),
    proxy: GatewayProxyService = Depends(get_proxy_service),
) -> Response:
    return await proxy.proxy_to_service("git", "/v1/git/checkout", request, json_body=payload.model_dump())


@router.post(
    "/commit",
    response_model=SuccessResponse[GitActionResponse],
    summary="Create Git Commit",
    description="Stages and commits working tree modifications.",
    responses={
        200: {"model": SuccessResponse[GitActionResponse], "description": "Commit created"},
    },
)
async def create_commit(
    payload: GitCommitRequest,
    request: Request,
    auth: dict = Depends(verify_auth_token),
    proxy: GatewayProxyService = Depends(get_proxy_service),
) -> Response:
    return await proxy.proxy_to_service("git", "/v1/git/commit", request, json_body=payload.model_dump())


@router.post(
    "/restore",
    response_model=SuccessResponse[GitActionResponse],
    summary="Discard Working Directory Modifications",
    description="Reverts modified/deleted files back to HEAD commit state.",
    responses={
        200: {"model": SuccessResponse[GitActionResponse], "description": "Files restored"},
    },
)
async def restore_files(
    payload: GitRestoreRequest,
    request: Request,
    auth: dict = Depends(verify_auth_token),
    proxy: GatewayProxyService = Depends(get_proxy_service),
) -> Response:
    return await proxy.proxy_to_service("git", "/v1/git/restore", request, json_body=payload.model_dump())


@router.post(
    "/stage",
    response_model=SuccessResponse[GitActionResponse],
    summary="Stage Working Tree Files",
    description="Stages specified files into the Git index (git add).",
    responses={
        200: {"model": SuccessResponse[GitActionResponse], "description": "Files staged"},
    },
)
async def stage_files(
    payload: GitStageRequest,
    request: Request,
    auth: dict = Depends(verify_auth_token),
    proxy: GatewayProxyService = Depends(get_proxy_service),
) -> Response:
    return await proxy.proxy_to_service("git", "/v1/git/stage", request, json_body=payload.model_dump())


@router.post(
    "/unstage",
    response_model=SuccessResponse[GitActionResponse],
    summary="Unstage Staged Files",
    description="Unstages specified files from the Git index (git restore --staged).",
    responses={
        200: {"model": SuccessResponse[GitActionResponse], "description": "Files unstaged"},
    },
)
async def unstage_files(
    payload: GitUnstageRequest,
    request: Request,
    auth: dict = Depends(verify_auth_token),
    proxy: GatewayProxyService = Depends(get_proxy_service),
) -> Response:
    return await proxy.proxy_to_service("git", "/v1/git/unstage", request, json_body=payload.model_dump())
