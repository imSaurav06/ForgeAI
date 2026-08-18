import re
from typing import Any

from services.retrieval.app.embeddings.vector_encoder import CodeVectorEncoder
from services.retrieval.app.qdrant.qdrant_client import get_qdrant_client
from services.retrieval.app.reranking.reranker import CodeRRFReranker


class RAGSearchPipeline:
    """
    Production Code RAG Search Pipeline executing:
    Intent Analysis -> Query Expansion -> Symbol Search -> Keyword Search -> Vector Search -> Dependency Search -> Rerank.
    """

    def __init__(self) -> None:
        self.qdrant_client = get_qdrant_client()

    def analyze_intent(self, query: str) -> dict[str, Any]:
        """Analyze user query intent and extract domain target keywords."""
        q_lower = query.lower()
        intent = "general"

        if any(w in q_lower for w in ["auth", "jwt", "login", "token", "password", "session"]):
            intent = "authentication"
        elif any(w in q_lower for w in ["api", "route", "endpoint", "post", "get", "rest"]):
            intent = "api_endpoint"
        elif any(w in q_lower for w in ["db", "database", "mongo", "query", "model", "schema"]):
            intent = "database"
        elif any(w in q_lower for w in ["test", "pytest", "mock", "assert"]):
            intent = "testing"

        return {"intent": intent, "original_query": query}

    def expand_query(self, query: str) -> list[str]:
        """Expand natural language query into technical code symbol keywords."""
        tokens = re.findall(r"[A-Za-z0-9_]+", query)
        expansions = set(tokens)

        # Add common code equivalents
        for t in list(tokens):
            tl = t.lower()
            if tl == "auth":
                expansions.update(["authentication", "jwt", "validate_token"])
            elif tl in ("health", "status"):
                expansions.update(["health_check", "get_health"])
            elif tl in ("user", "users"):
                expansions.update(["UserService", "user_id"])

        return list(expansions)

    def execute_hybrid_search(
        self,
        query: str,
        repository_id: str,
        indexed_points: list[dict[str, Any]],
        symbols_index: list[dict[str, Any]],
        dependency_graph: dict[str, Any],
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Execute full RAG hybrid retrieval pipeline.
        """
        # Step 1 & 2: Intent Analysis & Query Expansion
        intent_info = self.analyze_intent(query)
        expanded_keywords = self.expand_query(query)

        # Step 3: Vector Search via Qdrant
        query_vector = CodeVectorEncoder.encode(query)
        vector_matches = self.qdrant_client.search(
            query_vector=query_vector,
            repository_id=repository_id,
            limit=limit * 2,
        )

        # Step 4: Symbol Search
        symbol_matches: list[dict[str, Any]] = []
        for sym in symbols_index:
            sym_name = sym.get("symbol", "").lower()
            if any(kw.lower() in sym_name for kw in expanded_keywords):
                symbol_matches.append(
                    {
                        "file_path": sym.get("file"),
                        "start_line": sym.get("start_line", 1),
                        "end_line": sym.get("end_line", 1),
                        "symbol": sym.get("symbol"),
                        "symbol_type": sym.get("type"),
                        "snippet": sym.get("signature", ""),
                        "score": 0.9,
                    }
                )

        # Step 5: Keyword Search
        keyword_matches: list[dict[str, Any]] = []
        for pt in indexed_points:
            snippet = pt.get("snippet", "").lower()
            if any(kw.lower() in snippet for kw in expanded_keywords):
                keyword_matches.append(
                    {
                        "file_path": pt.get("file_path"),
                        "start_line": pt.get("start_line", 1),
                        "end_line": pt.get("end_line", 1),
                        "symbol": pt.get("symbol"),
                        "snippet": pt.get("snippet", ""),
                        "score": 0.7,
                    }
                )

        # Step 6: Dependency Search (Trace imports of top matches)
        top_files = {m.get("file_path") for m in vector_matches[:2] if m.get("file_path")}
        for edge in dependency_graph.get("internal_edges", []):
            if edge["source"] in top_files and edge["target"] not in top_files:
                keyword_matches.append(
                    {
                        "file_path": edge["target"],
                        "start_line": 1,
                        "end_line": 20,
                        "symbol": "imported_dependency",
                        "snippet": f"# Dependency imported by {edge['source']}",
                        "score": 0.6,
                    }
                )

        # Step 7: Rerank Results using Reciprocal Rank Fusion (RRF)
        reranked = CodeRRFReranker.rerank(
            vector_results=vector_matches,
            symbol_results=symbol_matches,
            keyword_results=keyword_matches,
            top_k=limit,
        )

        for item in reranked:
            item["intent"] = intent_info["intent"]

        return reranked
