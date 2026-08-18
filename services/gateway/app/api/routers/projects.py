from fastapi import APIRouter, Depends, Request, Response, status

from services.gateway.app.api.dependencies.auth import verify_auth_token
from services.gateway.app.api.dependencies.proxy import get_proxy_service
from services.gateway.app.schemas.projects import (
    ProjectCreateRequest,
    ProjectListResponse,
    ProjectResponse,
)
from services.gateway.app.services.proxy_service import GatewayProxyService
from shared.schemas.responses import ErrorResponse, SuccessResponse

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.post(
    "",
    response_model=SuccessResponse[ProjectResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Register New Project Workspace",
    description="Registers a local source code directory as a project workspace for intelligence and indexing.",
    responses={
        201: {"model": SuccessResponse[ProjectResponse], "description": "Project workspace registered successfully"},
        400: {"model": ErrorResponse, "description": "Invalid directory path or project settings"},
        503: {"model": ErrorResponse, "description": "Downstream service unavailable"},
    },
)
async def create_project(
    payload: ProjectCreateRequest,
    request: Request,
    auth: dict = Depends(verify_auth_token),
    proxy: GatewayProxyService = Depends(get_proxy_service),
) -> Response:
    return await proxy.proxy_to_service("repository", "/v1/repositories/register", request, json_body=payload.model_dump())


@router.get(
    "",
    response_model=SuccessResponse[ProjectListResponse],
    summary="List Projects",
    description="Retrieves all registered project workspaces.",
    responses={
        200: {"model": SuccessResponse[ProjectListResponse], "description": "Projects list retrieved"},
        503: {"model": ErrorResponse, "description": "Downstream service unavailable"},
    },
)
async def list_projects(
    request: Request,
    auth: dict = Depends(verify_auth_token),
    proxy: GatewayProxyService = Depends(get_proxy_service),
) -> Response:
    return await proxy.proxy_to_service("repository", "/v1/repositories/", request)


@router.get(
    "/{id}",
    response_model=SuccessResponse[ProjectResponse],
    summary="Get Project Details",
    description="Retrieves metadata for a specific project workspace ID.",
    responses={
        200: {"model": SuccessResponse[ProjectResponse], "description": "Project details found"},
        404: {"model": ErrorResponse, "description": "Project not found"},
        503: {"model": ErrorResponse, "description": "Downstream service unavailable"},
    },
)
async def get_project(
    id: str,
    request: Request,
    auth: dict = Depends(verify_auth_token),
    proxy: GatewayProxyService = Depends(get_proxy_service),
) -> Response:
    return await proxy.proxy_to_service("repository", f"/v1/projects/{id}", request)


@router.delete(
    "/{id}",
    response_model=SuccessResponse[dict],
    summary="Delete Project",
    description="Deletes a project workspace registration and clears its vector index.",
    responses={
        200: {"model": SuccessResponse[dict], "description": "Project deleted successfully"},
        404: {"model": ErrorResponse, "description": "Project not found"},
        503: {"model": ErrorResponse, "description": "Downstream service unavailable"},
    },
)
async def delete_project(
    id: str,
    request: Request,
    auth: dict = Depends(verify_auth_token),
    proxy: GatewayProxyService = Depends(get_proxy_service),
) -> Response:
    return await proxy.proxy_to_service("repository", f"/v1/projects/{id}", request)
