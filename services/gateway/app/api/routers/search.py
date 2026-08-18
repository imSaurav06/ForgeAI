from fastapi import APIRouter, Depends, Request, Response

from services.gateway.app.api.dependencies.auth import verify_auth_token
from services.gateway.app.api.dependencies.proxy import get_proxy_service
from services.gateway.app.schemas.search import (
    CodeSearchRequest,
    SearchMatch,
    SearchResponse,
    SemanticSearchRequest,
    SymbolSearchRequest,
)
from services.gateway.app.services.proxy_service import GatewayProxyService
from shared.schemas.responses import SuccessResponse

router = APIRouter(prefix="/search", tags=["Search & RAG"])


@router.post(
    "/code",
    response_model=SuccessResponse[SearchResponse],
    summary="Code Text Search",
    description="Performs regex/text query search across workspace repository files.",
)
async def search_code(
    payload: CodeSearchRequest,
    request: Request,
    auth: dict = Depends(verify_auth_token),
    proxy: GatewayProxyService = Depends(get_proxy_service),
) -> Response:
    return await proxy.proxy_to_service("repository", "/v1/search/code", request, json_body=payload.model_dump())


@router.post(
    "/semantic",
    response_model=SuccessResponse[SearchResponse],
    summary="Semantic Vector RAG Search",
    description="Performs dense vector similarity search in Qdrant collection.",
)
async def search_semantic(
    payload: SemanticSearchRequest,
    request: Request,
    auth: dict = Depends(verify_auth_token),
    proxy: GatewayProxyService = Depends(get_proxy_service),
) -> Response:
    retrieval_payload = {
        "repository_id": payload.effective_repo_id,
        "query": payload.query,
        "limit": payload.limit,
    }
    return await proxy.proxy_to_service("retrieval", "/v1/search/semantic", request, json_body=retrieval_payload)


@router.post(
    "/symbol",
    response_model=SuccessResponse[SearchResponse],
    summary="AST Symbol Search",
    description="Finds class, function, or method definitions by symbol identifier.",
)
async def search_symbol(
    payload: SymbolSearchRequest,
    request: Request,
    auth: dict = Depends(verify_auth_token),
    proxy: GatewayProxyService = Depends(get_proxy_service),
) -> Response:
    return await proxy.proxy_to_service("repository", "/v1/search/symbol", request, json_body=payload.model_dump())
