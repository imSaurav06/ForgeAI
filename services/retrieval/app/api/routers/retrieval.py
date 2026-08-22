from typing import Any

from fastapi import APIRouter, Query, status

from services.retrieval.app.schemas.retrieval_schemas import (
    ContextRequest,
    ContextResponse,
    EmbeddingIndexRequest,
    HybridSearchRequest,
    IndexStatusResponse,
    SearchMatchSnippet,
    SemanticSearchRequest,
)
from services.retrieval.app.services.retrieval_service import RetrievalService
from shared.schemas.responses import SuccessResponse

router = APIRouter(tags=["Code RAG & Retrieval"])
retrieval_service = RetrievalService()


@router.post(
    "/v1/search/semantic",
    response_model=SuccessResponse[list[SearchMatchSnippet]],
    summary="Semantic Vector Search",
    description="Performs dense vector similarity search against Qdrant collection.",
    responses={
        200: {"model": SuccessResponse[list[SearchMatchSnippet]], "description": "Semantic search matches"},
    },
)
async def search_semantic(payload: SemanticSearchRequest) -> SuccessResponse[list[SearchMatchSnippet]]:
    matches = await retrieval_service.semantic_search(
        repository_id=payload.repository_id, query=payload.query, limit=payload.limit
    )
    snippets = [
        SearchMatchSnippet(
            file_path=m.get("file_path", ""),
            start_line=m.get("start_line", 1),
            end_line=m.get("end_line", 1),
            symbol=m.get("symbol"),
            snippet=m.get("snippet", ""),
            score=m.get("score"),
        )
        for m in matches
    ]
    return SuccessResponse(data=snippets, message="Semantic vector search completed")


@router.post(
    "/v1/search/hybrid",
    response_model=SuccessResponse[list[dict[str, Any]]],
    summary="Hybrid RAG Search with RRF Reranking",
    description="Executes Intent Analysis -> Query Expansion -> Vector + Symbol + Keyword + Dependency Search -> RRF Reranking.",
    responses={
        200: {"model": SuccessResponse[list[dict[str, Any]]], "description": "Hybrid search matches"},
    },
)
async def search_hybrid(payload: HybridSearchRequest) -> SuccessResponse[list[dict[str, Any]]]:
    matches = await retrieval_service.hybrid_search(
        repository_id=payload.repository_id, query=payload.query, limit=payload.limit
    )
    return SuccessResponse(data=matches, message="Hybrid RAG search completed")


@router.post(
    "/v1/search/context",
    response_model=SuccessResponse[ContextResponse],
    summary="Build Prompt Context with Token Budgeting",
    description="Assembles formatted LLM prompt context strictly enforcing max_tokens token budgeting limit.",
    responses={
        200: {"model": SuccessResponse[ContextResponse], "description": "Context compiled successfully"},
    },
)
async def build_context(payload: ContextRequest) -> SuccessResponse[ContextResponse]:
    result = await retrieval_service.build_rag_context(
        repository_id=payload.repository_id, query=payload.query, max_tokens=payload.max_tokens
    )
    snippets = [
        SearchMatchSnippet(
            file_path=s.get("file_path", ""),
            start_line=s.get("start_line", 1),
            end_line=s.get("end_line", 1),
            symbol=s.get("symbol"),
            snippet=s.get("snippet", ""),
            score=s.get("score") or s.get("rrf_score"),
        )
        for s in result.get("snippets", [])
    ]
    ctx_resp = ContextResponse(
        repository_id=result["repository_id"],
        context_text=result["context_text"],
        total_tokens_used=result["total_tokens_used"],
        max_token_budget=result["max_token_budget"],
        snippet_count=result["snippet_count"],
        snippets=snippets,
    )
    return SuccessResponse(data=ctx_resp, message="RAG context assembled with token budget")


@router.post(
    "/v1/index/embeddings",
    response_model=SuccessResponse[IndexStatusResponse],
    status_code=status.HTTP_202_ACCEPTED,
    summary="Index Repository Vector Embeddings",
    description="Encodes 384-dim code vector embeddings and upserts points into Qdrant collection.",
    responses={
        202: {"model": SuccessResponse[IndexStatusResponse], "description": "Vector indexing initiated"},
    },
)
async def index_embeddings(payload: EmbeddingIndexRequest) -> SuccessResponse[IndexStatusResponse]:
    points_count = await retrieval_service.index_embeddings(
        repository_id=payload.repository_id, force_reindex=payload.force_reindex
    )
    resp = IndexStatusResponse(repository_id=payload.repository_id, indexed_points_count=points_count, status="completed")
    return SuccessResponse(data=resp, message="Vector embedding indexing completed")


@router.post(
    "/v1/repositories/{id}/index",
    response_model=SuccessResponse[IndexStatusResponse],
    status_code=status.HTTP_202_ACCEPTED,
    summary="Index Repository Vector Embeddings by ID",
    description="Encodes vector embeddings and upserts points into Qdrant for the specified repository.",
    responses={
        202: {"model": SuccessResponse[IndexStatusResponse], "description": "Vector indexing initiated"},
    },
)
async def index_repository_embeddings(
    id: str,
    payload: EmbeddingIndexRequest | None = None,
) -> SuccessResponse[IndexStatusResponse]:
    force = payload.force_reindex if payload else False
    repo_id = id or (payload.repository_id if payload else "")
    points_count = await retrieval_service.index_embeddings(
        repository_id=repo_id, force_reindex=force
    )
    resp = IndexStatusResponse(repository_id=repo_id, indexed_points_count=points_count, status="completed")
    return SuccessResponse(data=resp, message="Vector embedding indexing completed")


@router.get(
    "/v1/index/status",
    response_model=SuccessResponse[IndexStatusResponse],
    summary="Get Qdrant Vector Index Status",
    description="Returns vector points count and index status for a repository.",
    responses={
        200: {"model": SuccessResponse[IndexStatusResponse], "description": "Index status retrieved"},
    },
)
async def get_index_status(
    repository_id: str = Query(..., description="Target repository ID")
) -> SuccessResponse[IndexStatusResponse]:
    qdrant = retrieval_service.qdrant
    matches = qdrant.search(query_vector=[0.0] * 384, repository_id=repository_id, limit=1000)
    resp = IndexStatusResponse(repository_id=repository_id, indexed_points_count=len(matches), status="completed")
    return SuccessResponse(data=resp, message="Index status retrieved")


@router.post(
    "/v1/search/related-code",
    response_model=SuccessResponse[list[dict[str, Any]]],
    summary="Retrieve Related Code",
    description="Finds relevant code context for target symbol or file.",
)
async def retrieve_related_code_endpoint(
    payload: dict[str, Any],
) -> SuccessResponse[list[dict[str, Any]]]:
    repo_id = payload.get("repository_id", "")
    query = payload.get("query", "")
    limit = payload.get("limit", 5)
    results = await retrieval_service.retrieve_related_code(repo_id, query, limit=limit)
    return SuccessResponse(data=results, message="Related code retrieved")


@router.post(
    "/v1/search/tests",
    response_model=SuccessResponse[list[dict[str, Any]]],
    summary="Retrieve Tests",
    description="Finds test files and functions for target module.",
)
async def retrieve_tests_endpoint(
    payload: dict[str, Any],
) -> SuccessResponse[list[dict[str, Any]]]:
    repo_id = payload.get("repository_id", "")
    module_name = payload.get("module_name") or payload.get("query", "")
    limit = payload.get("limit", 5)
    results = await retrieval_service.retrieve_tests(repo_id, module_name, limit=limit)
    return SuccessResponse(data=results, message="Tests retrieved")


@router.post(
    "/v1/search/documentation",
    response_model=SuccessResponse[list[dict[str, Any]]],
    summary="Retrieve Documentation",
    description="Finds relevant documentation files and markdown snippets.",
)
async def retrieve_documentation_endpoint(
    payload: dict[str, Any],
) -> SuccessResponse[list[dict[str, Any]]]:
    repo_id = payload.get("repository_id", "")
    query = payload.get("query", "")
    limit = payload.get("limit", 5)
    results = await retrieval_service.retrieve_documentation(repo_id, query, limit=limit)
    return SuccessResponse(data=results, message="Documentation retrieved")

