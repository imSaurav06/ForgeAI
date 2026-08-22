"""
Qdrant Vector Database Client wrapping official qdrant_client library.

Manages collection 'forge_ai_code', stores code embeddings and rich metadata,
and executes vector similarity search and payload filtering directly in Qdrant.
"""

from __future__ import annotations

import uuid
from typing import Any

from qdrant_client import QdrantClient, models
from qdrant_client.http.exceptions import UnexpectedResponse

from services.retrieval.app.embeddings.vector_encoder import CodeVectorEncoder
from shared.config.settings import get_settings
from shared.logging.logger import logger


class VectorPoint:
    """Vector record point structure returned from Qdrant vector database."""

    def __init__(
        self,
        point_id: str,
        embedding: list[float],
        payload: dict[str, Any],
    ) -> None:
        self.id = point_id
        self.embedding = embedding
        self.payload = payload


class ForgeQdrantClient:
    """
    Real Qdrant Vector Database Client wrapping qdrant_client.QdrantClient.
    Executes vector operations, metadata filtering, collection management,
    and point lifecycle directly against Qdrant.
    """

    def __init__(
        self,
        collection_name: str | None = None,
        location: str | None = None,
        url: str | None = None,
        host: str | None = None,
        port: int | None = None,
        client: QdrantClient | None = None,
    ) -> None:
        settings = get_settings()
        self.collection_name = collection_name or settings.qdrant_collection_name
        self.qdrant_host = host or settings.qdrant_host
        self.qdrant_port = port or settings.qdrant_port
        self.qdrant_url = url or settings.qdrant_url
        self.qdrant_location = location

        if client is not None:
            self._client = client
        elif location is not None:
            logger.info(f"Initializing Qdrant client with location='{location}'")
            self._client = QdrantClient(location=location)
        elif url is not None:
            logger.info(f"Initializing Qdrant client with url='{url}'")
            self._client = QdrantClient(url=url)
        elif host is not None or port is not None:
            logger.info(f"Initializing Qdrant client with host='{self.qdrant_host}', port={self.qdrant_port}")
            self._client = QdrantClient(host=self.qdrant_host, port=self.qdrant_port)
        elif settings.qdrant_location is not None:
            logger.info(f"Initializing Qdrant client with settings location='{settings.qdrant_location}'")
            self._client = QdrantClient(location=settings.qdrant_location)
        elif settings.qdrant_url is not None:
            logger.info(f"Initializing Qdrant client with settings url='{settings.qdrant_url}'")
            self._client = QdrantClient(url=settings.qdrant_url)
        else:
            logger.info(f"Initializing Qdrant client with host='{self.qdrant_host}', port={self.qdrant_port}")
            self._client = QdrantClient(host=self.qdrant_host, port=self.qdrant_port)

    @property
    def client(self) -> QdrantClient:
        return self._client

    @classmethod
    def generate_point_id(
        cls,
        repository_id: str,
        file_path: str,
        symbol: str | None = None,
        start_line: int = 1,
        chunk_hash: str = "",
    ) -> str:
        """
        Generate a deterministic UUID5 point ID string based on repository, path, symbol, line, and hash.
        Guarantees stable IDs across repeated re-indexing of unchanged code.
        """
        canonical_key = f"{repository_id}:{file_path}:{symbol or ''}:{start_line}:{chunk_hash}"
        return str(uuid.uuid5(uuid.NAMESPACE_URL, canonical_key))

    def ensure_collection_exists(self, vector_size: int = 384) -> bool:
        """Ensure collection exists in Qdrant; create it if missing."""
        try:
            if not self._client.collection_exists(self.collection_name):
                logger.info(
                    f"Collection '{self.collection_name}' does not exist in Qdrant. "
                    f"Creating with vector_size={vector_size}, COSINE distance."
                )
                self._client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=models.VectorParams(
                        size=vector_size,
                        distance=models.Distance.COSINE,
                    ),
                )
            return True
        except Exception as err:
            logger.error(f"Failed to ensure collection '{self.collection_name}' exists in Qdrant: {err}")
            raise

    def recreate_collection(self, vector_size: int = 384) -> bool:
        """Recreate collection in Qdrant (explicit override)."""
        try:
            if self._client.collection_exists(self.collection_name):
                self._client.delete_collection(self.collection_name)
            return self.ensure_collection_exists(vector_size=vector_size)
        except Exception as err:
            logger.error(f"Failed to recreate collection '{self.collection_name}' in Qdrant: {err}")
            raise

    def get_collection_info(self) -> dict[str, Any]:
        """Retrieve Qdrant collection status and statistics."""
        try:
            self.ensure_collection_exists()
            info = self._client.get_collection(self.collection_name)
            return {
                "collection_name": self.collection_name,
                "status": str(info.status),
                "points_count": info.points_count,
                "vectors_count": getattr(info, "indexed_vectors_count", info.points_count),
            }
        except Exception as err:
            logger.error(f"Error getting collection info for '{self.collection_name}': {err}")
            return {
                "collection_name": self.collection_name,
                "status": "error",
                "points_count": 0,
                "vectors_count": 0,
                "error": str(err),
            }

    def upsert_points(self, repository_id: str, points: list[dict[str, Any]]) -> int:
        """
        Upsert vector points into Qdrant collection.
        Each point must contain file_path, language, symbol, start_line, end_line, chunk_hash, etc.
        """
        if not points:
            return 0

        self.ensure_collection_exists()

        batch_structs: list[models.PointStruct] = []
        for pt in points:
            file_path = pt.get("file_path", "")
            symbol = pt.get("symbol")
            start_line = pt.get("start_line", 1)
            chunk_hash = pt.get("chunk_hash", "")

            point_id = pt.get("id") or self.generate_point_id(
                repository_id=repository_id,
                file_path=file_path,
                symbol=symbol,
                start_line=start_line,
                chunk_hash=chunk_hash,
            )

            raw_embedding = pt.get("embedding")
            if not raw_embedding:
                raw_embedding = CodeVectorEncoder.encode(pt.get("snippet", ""))

            embedding = [float(v) for v in raw_embedding]

            payload = {
                "repository_id": repository_id,
                "file_path": file_path,
                "language": pt.get("language", "python"),
                "symbol": symbol,
                "symbol_type": pt.get("symbol_type"),
                "start_line": start_line,
                "end_line": pt.get("end_line", 1),
                "chunk_hash": chunk_hash,
                "git_commit": pt.get("git_commit", "HEAD"),
                "dependency_metadata": pt.get("dependency_metadata", {}),
                "snippet": pt.get("snippet", ""),
            }

            batch_structs.append(
                models.PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload=payload,
                )
            )

        try:
            self._client.upsert(
                collection_name=self.collection_name,
                points=batch_structs,
            )
            logger.info(
                f"Upserted {len(batch_structs)} vector points into Qdrant collection '{self.collection_name}' for repo '{repository_id}'"
            )
            return len(batch_structs)
        except Exception as err:
            logger.error(f"Failed upserting points to Qdrant collection '{self.collection_name}': {err}")
            raise

    def search(
        self,
        query_vector: list[float],
        repository_id: str,
        limit: int = 5,
        language: str | None = None,
        symbol_type: str | None = None,
        file_path: str | None = None,
    ) -> list[dict[str, Any]]:
        """Perform vector similarity search against Qdrant collection using payload filters."""
        self.ensure_collection_exists()

        must_conditions: list[models.Condition] = [
            models.FieldCondition(
                key="repository_id",
                match=models.MatchValue(value=repository_id),
            )
        ]
        if language:
            must_conditions.append(
                models.FieldCondition(key="language", match=models.MatchValue(value=language))
            )
        if symbol_type:
            must_conditions.append(
                models.FieldCondition(key="symbol_type", match=models.MatchValue(value=symbol_type))
            )
        if file_path:
            must_conditions.append(
                models.FieldCondition(key="file_path", match=models.MatchValue(value=file_path))
            )

        query_filter = models.Filter(must=must_conditions)
        float_vector = [float(v) for v in query_vector]

        try:
            query_response = self._client.query_points(
                collection_name=self.collection_name,
                query=float_vector,
                query_filter=query_filter,
                limit=limit,
            )
            points = query_response.points
        except (AttributeError, UnexpectedResponse):
            # Fallback to search if query_points not supported in client version
            points = self._client.search(
                collection_name=self.collection_name,
                query_vector=float_vector,
                query_filter=query_filter,
                limit=limit,
            )
        except Exception as err:
            logger.error(f"Qdrant vector search failed: {err}")
            raise

        matches: list[dict[str, Any]] = []
        for pt in points:
            match = dict(pt.payload or {})
            match["score"] = round(float(pt.score), 4)
            matches.append(match)

        return matches

    def clear_repository_points(self, repository_id: str) -> int:
        """Delete all vector points belonging to a repository from Qdrant."""
        try:
            self.ensure_collection_exists()
            delete_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="repository_id",
                        match=models.MatchValue(value=repository_id),
                    )
                ]
            )
            self._client.delete(
                collection_name=self.collection_name,
                points_selector=delete_filter,
            )
            logger.info(f"Deleted vector points for repository '{repository_id}' from Qdrant")
            return 1
        except Exception as err:
            logger.error(f"Failed deleting points for repository '{repository_id}' from Qdrant: {err}")
            raise

    def delete_file_points(self, repository_id: str, file_path: str) -> int:
        """Delete all vector points belonging to a specific file in a repository."""
        try:
            self.ensure_collection_exists()
            delete_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="repository_id",
                        match=models.MatchValue(value=repository_id),
                    ),
                    models.FieldCondition(
                        key="file_path",
                        match=models.MatchValue(value=file_path),
                    ),
                ]
            )
            self._client.delete(
                collection_name=self.collection_name,
                points_selector=delete_filter,
            )
            logger.info(f"Deleted vector points for file '{file_path}' in repo '{repository_id}' from Qdrant")
            return 1
        except Exception as err:
            logger.error(f"Failed deleting points for file '{file_path}' in Qdrant: {err}")
            raise

    def check_health(self) -> dict[str, Any]:
        """Check Qdrant server connectivity and collection status."""
        try:
            collections = self._client.get_collections()
            has_collection = any(c.name == self.collection_name for c in collections.collections)
            return {
                "status": "healthy",
                "qdrant_connected": True,
                "collection_name": self.collection_name,
                "collection_exists": has_collection,
            }
        except Exception as err:
            logger.warning(f"Qdrant health check failed: {err}")
            return {
                "status": "unhealthy",
                "qdrant_connected": False,
                "collection_name": self.collection_name,
                "error": str(err),
            }


_qdrant_client_instance: ForgeQdrantClient | None = None


def get_qdrant_client(
    location: str | None = None,
    url: str | None = None,
    host: str | None = None,
    port: int | None = None,
    client: QdrantClient | None = None,
) -> ForgeQdrantClient:
    """Accessor for global ForgeQdrantClient instance."""
    global _qdrant_client_instance
    if client is not None or location is not None or url is not None or host is not None or port is not None:
        return ForgeQdrantClient(
            location=location,
            url=url,
            host=host,
            port=port,
            client=client,
        )
    if _qdrant_client_instance is None:
        _qdrant_client_instance = ForgeQdrantClient()
    return _qdrant_client_instance
