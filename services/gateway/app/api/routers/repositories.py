from fastapi import APIRouter, Depends, Request, Response, status

from services.gateway.app.api.dependencies.auth import verify_auth_token
from services.gateway.app.api.dependencies.proxy import get_proxy_service
from services.gateway.app.schemas.repositories import (
    CloneRepoRequest,
    FilesystemBrowseResponse,
    IndexRepoRequest,
    OpenRepoRequest,
    RepoStatusResponse,
    RepoTreeNode,
    FileWriteRequest,
)
from services.gateway.app.services.proxy_service import GatewayProxyService
from shared.schemas.responses import ErrorResponse, SuccessResponse

router = APIRouter(prefix="/repositories", tags=["Repositories"])


@router.get(
    "/browse",
    response_model=SuccessResponse[FilesystemBrowseResponse],
    summary="Browse Local Filesystem Directories",
    description="Returns available drives, current path, parent, and subdirectories for folder navigation.",
    responses={
        200: {"model": SuccessResponse[FilesystemBrowseResponse], "description": "Filesystem directory listing retrieved"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
    },
)
async def browse_filesystem(
    request: Request,
    auth: dict = Depends(verify_auth_token),
    proxy: GatewayProxyService = Depends(get_proxy_service),
) -> Response:
    return await proxy.proxy_to_service("repository", "/v1/repositories/browse", request)


@router.get(
    "",
    response_model=SuccessResponse[list[dict]],
    summary="List Registered Repositories",
    description="Returns all registered repository metadata records for the authenticated user.",
    responses={
        200: {"model": SuccessResponse[list[dict]], "description": "Repositories list retrieved"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
    },
)
async def list_repositories(
    request: Request,
    auth: dict = Depends(verify_auth_token),
    proxy: GatewayProxyService = Depends(get_proxy_service),
) -> Response:
    return await proxy.proxy_to_service("repository", "/v1/repositories", request)


@router.post(
    "/open",
    response_model=SuccessResponse[RepoStatusResponse],
    summary="Open Local Repository",
    description="Registers and inspects a local repository directory.",
    responses={
        200: {"model": SuccessResponse[RepoStatusResponse], "description": "Repository opened"},
        400: {"model": ErrorResponse, "description": "Invalid directory path"},
    },
)
async def open_repository(
    payload: OpenRepoRequest,
    request: Request,
    auth: dict = Depends(verify_auth_token),
    proxy: GatewayProxyService = Depends(get_proxy_service),
) -> Response:
    return await proxy.proxy_to_service("repository", "/v1/repositories/open", request, json_body=payload.model_dump())



@router.post(
    "/clone",
    response_model=SuccessResponse[RepoStatusResponse],
    status_code=status.HTTP_202_ACCEPTED,
    summary="Clone Git Repository",
    description="Clones a remote repository URL locally.",
    responses={
        202: {"model": SuccessResponse[RepoStatusResponse], "description": "Cloning started"},
        400: {"model": ErrorResponse, "description": "Invalid git URL"},
    },
)
async def clone_repository(
    payload: CloneRepoRequest,
    request: Request,
    auth: dict = Depends(verify_auth_token),
    proxy: GatewayProxyService = Depends(get_proxy_service),
) -> Response:
    return await proxy.proxy_to_service("repository", "/v1/repositories/clone", request, json_body=payload.model_dump())


@router.post(
    "/{id}/index",
    response_model=SuccessResponse[RepoStatusResponse],
    summary="Index Repository Vector RAG",
    description="Parses AST symbols and generates Qdrant embeddings for code search.",
    responses={
        200: {"model": SuccessResponse[RepoStatusResponse], "description": "Indexing started"},
        404: {"model": ErrorResponse, "description": "Repository not found"},
    },
)
async def index_repository(
    id: str,
    payload: IndexRepoRequest,
    request: Request,
    auth: dict = Depends(verify_auth_token),
    proxy: GatewayProxyService = Depends(get_proxy_service),
) -> Response:
    return await proxy.proxy_to_service("retrieval", f"/v1/repositories/{id}/index", request, json_body=payload.model_dump())


@router.get(
    "/{id}/tree",
    response_model=SuccessResponse[list[RepoTreeNode]],
    summary="Get Repository File Tree",
    description="Returns the filtered source code directory file tree hierarchy.",
    responses={
        200: {"model": SuccessResponse[list[RepoTreeNode]], "description": "Tree hierarchy retrieved"},
        404: {"model": ErrorResponse, "description": "Repository not found"},
    },
)
async def get_repository_tree(
    id: str,
    request: Request,
    auth: dict = Depends(verify_auth_token),
    proxy: GatewayProxyService = Depends(get_proxy_service),
) -> Response:
    return await proxy.proxy_to_service("repository", f"/v1/repositories/{id}/tree", request)


@router.get(
    "/{id}/status",
    response_model=SuccessResponse[RepoStatusResponse],
    summary="Get Repository Indexing Status",
    description="Retrieves current parsing and indexing progress.",
    responses={
        200: {"model": SuccessResponse[RepoStatusResponse], "description": "Status retrieved"},
        404: {"model": ErrorResponse, "description": "Repository not found"},
    },
)
async def get_repository_status(
    id: str,
    request: Request,
    auth: dict = Depends(verify_auth_token),
    proxy: GatewayProxyService = Depends(get_proxy_service),
) -> Response:
    return await proxy.proxy_to_service("repository", f"/v1/repositories/{id}/status", request)


@router.get(
    "/{id}/file",
    summary="Get File Content",
    description="Reads content of a file within the repository by its relative path.",
)
async def get_repository_file(
    id: str,
    path: str,
    request: Request,
    auth: dict = Depends(verify_auth_token),
    proxy: GatewayProxyService = Depends(get_proxy_service),
) -> Response:
    return await proxy.proxy_to_service(
        "repository",
        f"/v1/repositories/{id}/file",
        request,
        params={"path": path},
    )


@router.get(
    "/{id}",
    summary="Get Repository Details",
    description="Returns metadata for the repository ID.",
)
async def get_repository_details(
    id: str,
    request: Request,
    auth: dict = Depends(verify_auth_token),
    proxy: GatewayProxyService = Depends(get_proxy_service),
) -> Response:
    return await proxy.proxy_to_service("repository", f"/v1/repositories/{id}", request)


@router.post(
    "/{id}/files",
    summary="Create or Update File",
    description="Writes text content to a target file.",
)
async def create_or_update_file(
    id: str,
    payload: FileWriteRequest,
    request: Request,
    auth: dict = Depends(verify_auth_token),
    proxy: GatewayProxyService = Depends(get_proxy_service),
) -> Response:
    return await proxy.proxy_to_service(
        "tools", 
        "/internal/v1/tools/write-file", 
        request, 
        json_body={"path": payload.path, "content": payload.content, "repository_id": id},
        method="POST"
    )

