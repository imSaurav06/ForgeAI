
from pydantic import BaseModel, Field


class SemanticSearchRequest(BaseModel):
    """Request payload for semantic vector search."""

    repository_id: str = Field(..., description="Target repository ID")
    query: str = Field(..., description="Query string", json_schema_extra={"example": "JWT authentication token validation"})
    limit: int = Field(default=5, ge=1, le=50, description="Max result count")


class HybridSearchRequest(BaseModel):
    """Request payload for hybrid (vector + symbol + keyword) search."""

    repository_id: str = Field(..., description="Target repository ID")
    query: str = Field(..., description="User prompt query string", json_schema_extra={"example": "How is refresh token stored?"})
    limit: int = Field(default=5, ge=1, le=50, description="Max result count")


class ContextRequest(BaseModel):
    """Request payload to assemble RAG context with token budgeting."""

    repository_id: str = Field(..., description="Target repository ID")
    query: str = Field(..., description="User prompt query")
    max_tokens: int = Field(default=4096, ge=128, le=16384, description="Max token budget limit")


class EmbeddingIndexRequest(BaseModel):
    """Request payload to trigger vector embedding indexing."""

    repository_id: str = Field(default="", description="Target repository ID")
    force_reindex: bool = Field(default=False, description="Clear existing collection points before indexing")


class SearchMatchSnippet(BaseModel):
    """Search match snippet model."""

    file_path: str = Field(..., description="Relative file path")
    start_line: int = Field(..., description="Start line number")
    end_line: int = Field(..., description="End line number")
    symbol: str | None = Field(default=None, description="AST symbol name")
    snippet: str = Field(..., description="Source code text snippet")
    score: float | None = Field(default=None, description="Similarity or RRF score")


class ContextResponse(BaseModel):
    """Assembled RAG context response model."""

    repository_id: str = Field(..., description="Repository ID")
    context_text: str = Field(..., description="Formatted context string for LLM prompt")
    total_tokens_used: int = Field(..., description="Total estimated tokens used")
    max_token_budget: int = Field(..., description="Requested max token budget")
    snippet_count: int = Field(..., description="Count of included snippets")
    snippets: list[SearchMatchSnippet] = Field(default_factory=list, description="Included snippet details")


class IndexStatusResponse(BaseModel):
    """Vector index status response model."""

    repository_id: str = Field(..., description="Repository ID")
    indexed_points_count: int = Field(..., description="Total vector points stored in Qdrant")
    status: str = Field(default="completed", description="Index status")
