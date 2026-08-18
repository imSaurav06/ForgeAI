from typing import Any

import httpx

from services.retrieval.app.context.context_builder import ContextBuilder
from services.retrieval.app.embeddings.vector_encoder import get_code_vector_encoder
from services.retrieval.app.qdrant.qdrant_client import get_qdrant_client
from services.retrieval.app.search.pipeline import RAGSearchPipeline
from shared.config.settings import get_settings
from shared.logging.logger import logger


class RetrievalService:
    """Retrieval & Code RAG Service managing real semantic vector indexing in Qdrant and hybrid context retrieval."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.qdrant = get_qdrant_client()
        self.pipeline = RAGSearchPipeline()
        self.encoder = get_code_vector_encoder()

    async def _fetch_repo_data(self, repository_id: str) -> dict[str, Any]:
        """Fetch scanned repository tree, files, symbols, and dependency graph from Repository Service."""
        # 1. Direct in-process lookup if available
        try:
            from services.repository.app.services.repository_service import RepositoryService
            repo_svc = RepositoryService()
            meta = repo_svc.get_repository_metadata(repository_id)
            if meta and meta.path:
                scan_res = repo_svc.scan_repository(repository_id)
                symbols_data = repo_svc.get_symbols(repository_id)
                graph_data = repo_svc.get_dependencies(repository_id)
                files_data = scan_res.get("files", [])
                if files_data or symbols_data:
                    return {"files": files_data, "symbols": symbols_data, "graph": graph_data}
        except Exception as err:
            logger.debug(f"Direct RepositoryService lookup exception for '{repository_id}': {err}")

        # 2. HTTP internal request lookup with HMAC authentication headers
        repo_service_url = self.settings.repository_service_url.rstrip("/")
        try:
            from services.gateway.app.core.internal_auth import InternalAuthManager
            headers = InternalAuthManager().inject_internal_headers({})
            async with httpx.AsyncClient(timeout=10.0) as client:
                files_res = await client.get(f"{repo_service_url}/v1/repositories/{repository_id}/files", headers=headers)
                symbols_res = await client.get(f"{repo_service_url}/v1/repositories/{repository_id}/symbols", headers=headers)
                deps_res = await client.get(f"{repo_service_url}/v1/repositories/{repository_id}/dependencies", headers=headers)

                files = files_res.json().get("data", []) if files_res.status_code == 200 else []
                symbols = symbols_res.json().get("data", []) if symbols_res.status_code == 200 else []
                graph = deps_res.json().get("data", {}) if deps_res.status_code == 200 else {}

                return {"files": files, "symbols": symbols, "graph": graph}
        except Exception as err:
            logger.warning(f"Could not reach Repository Service at {repo_service_url}: {err}")

        return {"files": [], "symbols": [], "graph": {}}

    async def index_embeddings(self, repository_id: str, force_reindex: bool = False) -> int:
        """Fetch repo files and AST symbols, batch encode real semantic vectors, and upsert points into Qdrant."""
        if force_reindex:
            self.qdrant.clear_repository_points(repository_id)

        repo_data = await self._fetch_repo_data(repository_id)
        scanned_files = repo_data["files"]
        symbols = repo_data["symbols"]

        points: list[dict[str, Any]] = []
        snippets_to_embed: list[str] = []

        # Prepare file points
        for f in scanned_files:
            snippet = f"Language: {f.get('language', 'python')}\nFile: {f['path']}\nType: file"
            snippets_to_embed.append(snippet)
            points.append(
                {
                    "file_path": f["path"],
                    "language": f.get("language", "python"),
                    "symbol": None,
                    "symbol_type": "file",
                    "start_line": 1,
                    "end_line": 1,
                    "chunk_hash": f.get("sha256", ""),
                    "snippet": snippet,
                }
            )

        # Prepare symbol points
        for sym in symbols:
            parent_str = f"\nParent: {sym.get('parent')}" if sym.get("parent") else ""
            sig_str = f"\nSignature: {sym.get('signature')}" if sym.get("signature") else ""
            snippet = f"Language: {sym.get('language', 'python')}\nFile: {sym.get('file')}\nSymbol: {sym.get('symbol')}\nType: {sym.get('type')}{parent_str}{sig_str}"
            snippets_to_embed.append(snippet)
            points.append(
                {
                    "file_path": sym.get("file"),
                    "language": sym.get("language", "python"),
                    "symbol": sym.get("symbol"),
                    "symbol_type": sym.get("type"),
                    "start_line": sym.get("start_line", 1),
                    "end_line": sym.get("end_line", 1),
                    "chunk_hash": "",
                    "snippet": snippet,
                }
            )

        if not points:
            return 0

        # Cap batch to top 50 points for fast local neural encoding
        max_batch = 50
        points = points[:max_batch]
        snippets_to_embed = snippets_to_embed[:max_batch]

        # Batch encode real dense semantic vectors
        vectors = self.encoder.encode_batch(snippets_to_embed)

        for point_dict, vec in zip(points, vectors, strict=False):
            point_dict["embedding"] = vec

        return self.qdrant.upsert_points(repository_id, points)

    async def semantic_search(self, repository_id: str, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Perform real semantic vector search in Qdrant using pretrained model query embeddings."""
        query_vector = self.encoder.encode(query)
        matches = self.qdrant.search(query_vector=query_vector, repository_id=repository_id, limit=limit)

        if not matches:
            # Re-index repository points if empty
            await self.index_embeddings(repository_id)
            matches = self.qdrant.search(query_vector=query_vector, repository_id=repository_id, limit=limit)

        return matches

    async def hybrid_search(self, repository_id: str, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Perform multi-signal RAG hybrid search with RRF reranking."""
        repo_data = await self._fetch_repo_data(repository_id)
        indexed_points = repo_data["files"]
        symbols_index = repo_data["symbols"]
        graph = repo_data["graph"]

        # Guarantee vector points exist
        await self.index_embeddings(repository_id)

        results = self.pipeline.execute_hybrid_search(
            query=query,
            repository_id=repository_id,
            indexed_points=indexed_points,
            symbols_index=symbols_index,
            dependency_graph=graph,
            limit=limit,
        )
        return results

    async def build_rag_context(self, repository_id: str, query: str, max_tokens: int = 4096) -> dict[str, Any]:
        """Execute hybrid search and assemble LLM prompt context within max_tokens budget."""
        retrieved_snippets = await self.hybrid_search(repository_id=repository_id, query=query, limit=10)
        context_result = ContextBuilder.build_context(
            retrieved_snippets=retrieved_snippets,
            max_token_budget=max_tokens,
        )
        context_result["repository_id"] = repository_id
        return context_result

    async def retrieve_related_code(self, repository_id: str, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Retrieve code snippets related to a given symbol or file."""
        return await self.hybrid_search(repository_id=repository_id, query=query, limit=limit)

    async def retrieve_tests(self, repository_id: str, module_name: str, limit: int = 5) -> list[dict[str, Any]]:
        """Retrieve test files and test functions related to a module."""
        repo_data = await self._fetch_repo_data(repository_id)
        files = repo_data.get("files", [])
        test_files = [
            f for f in files
            if "test" in f.get("path", "").lower() or (module_name.lower() in f.get("path", "").lower() and "test" in f.get("path", "").lower())
        ]
        results = []
        for tf in test_files[:limit]:
            results.append({
                "file_path": tf.get("path"),
                "snippet": f"# Test suite for {module_name} in {tf.get('path')}",
                "start_line": 1,
                "end_line": 1,
                "score": 1.0,
                "type": "test_file",
            })
        if not results:
            return await self.semantic_search(repository_id=repository_id, query=f"test {module_name}", limit=limit)
        return results

    async def retrieve_documentation(self, repository_id: str, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Retrieve markdown and documentation snippets for a query."""
        repo_data = await self._fetch_repo_data(repository_id)
        files = repo_data.get("files", [])
        doc_files = [f for f in files if f.get("path", "").lower().endswith((".md", ".rst", ".txt")) or "doc" in f.get("path", "").lower()]
        results = []
        q_lower = query.lower()
        for df in doc_files[:limit]:
            results.append({
                "file_path": df.get("path"),
                "snippet": f"# Documentation: {df.get('path')}",
                "start_line": 1,
                "end_line": 1,
                "score": 0.9,
                "type": "documentation",
            })
        if not results:
            return await self.semantic_search(repository_id=repository_id, query=f"documentation {query}", limit=limit)
        return results

