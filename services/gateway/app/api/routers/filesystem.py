from fastapi import APIRouter, Depends, Request, Response

from services.gateway.app.api.dependencies.auth import verify_auth_token
from services.gateway.app.api.dependencies.proxy import get_proxy_service
from services.gateway.app.schemas.repositories import FilesystemBrowseResponse
from services.gateway.app.services.proxy_service import GatewayProxyService
from shared.schemas.responses import ErrorResponse, SuccessResponse

router = APIRouter(prefix="/filesystem", tags=["Filesystem"])


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
    """Proxy directory browsing to Repository Service with authentication and permission verification."""
    return await proxy.proxy_to_service("repository", "/v1/repositories/browse", request)
