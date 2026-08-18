from typing import Any

from pydantic import BaseModel, Field


class CodeSearchRequest(BaseModel):
    """Literal keyword / regex code search request."""

    project_id: str = Field(..., description="Project workspace ID")
    query: str = Field(..., description="Keyword query string", json_schema_extra={"example": "JWT_SECRET"})
    file_pattern: str | None = Field(default=None, description="Optional glob file pattern e.g. *.py")


class SemanticSearchRequest(BaseModel):
    """Vector RAG semantic search request."""

    repository_id: str | None = Field(default=None, description="Target repository ID")
    project_id: str | None = Field(default=None, description="Project workspace ID")
    query: str = Field(..., description="Natural language semantic query", json_schema_extra={"example": "How is token expiration handled?"})
    limit: int = Field(default=5, ge=1, le=50, description="Maximum number of context snippets")

    @property
    def effective_repo_id(self) -> str:
        res = self.repository_id or self.project_id
        if not res:
            raise ValueError("Either repository_id or project_id must be provided")
        return res


class SymbolSearchRequest(BaseModel):
    """AST Symbol search request."""

    project_id: str = Field(..., description="Project workspace ID")
    symbol_name: str = Field(..., description="Class, function, or symbol name", json_schema_extra={"example": "validate_token"})
    symbol_type: str | None = Field(default=None, description="Optional symbol type filter: function, class, interface")


class SearchMatchItem(BaseModel):
    """Search match snippet item."""

    file_path: str = Field(..., description="Source code relative file path")
    start_line: int = Field(..., description="Starting line number")
    end_line: int = Field(..., description="Ending line number")
    symbol: str | None = Field(default=None, description="Enclosing AST symbol if available")
    score: float | None = Field(default=None, description="Relevance score for semantic search")
    snippet: str = Field(..., description="Source code text snippet")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional context metadata")


class SearchResponse(BaseModel):
    """Unified search response wrapper."""

    query: str = Field(..., description="Executed query string")
    matches: list[SearchMatchItem] = Field(default_factory=list, description="Matched code snippets array")
    total_matches: int = Field(default=0, description="Total match count")


SearchMatch = SearchMatchItem

