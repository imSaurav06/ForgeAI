"""
Real Qdrant Vector Database Integration Tests.

Validates collection management, deterministic point IDs, point upserts,
payload filtering, vector similarity search, point deletions, incremental re-indexing,
health checks, and Qdrant-unavailable error handling using official qdrant-client.
"""

import pytest

from services.retrieval.app.embeddings.vector_encoder import CodeVectorEncoder
from services.retrieval.app.qdrant.qdrant_client import ForgeQdrantClient


@pytest.fixture
def memory_qdrant() -> ForgeQdrantClient:
    """Fixture providing a ForgeQdrantClient backed by qdrant_client in memory mode."""
    client = ForgeQdrantClient(collection_name="test_forge_qdrant_real", location=":memory:")
    client.recreate_collection(vector_size=384)
    return client


def test_qdrant_collection_lifecycle(memory_qdrant: ForgeQdrantClient):
    """Verify collection existence, creation, and metadata retrieving."""
    assert memory_qdrant.ensure_collection_exists(vector_size=384) is True
    info = memory_qdrant.get_collection_info()
    assert info["collection_name"] == "test_forge_qdrant_real"
    assert "status" in info
    assert info["points_count"] == 0


def test_qdrant_deterministic_point_id():
    """Point IDs must be deterministic UUID5 strings across identical inputs."""
    id1 = ForgeQdrantClient.generate_point_id("repo_1", "src/auth.py", "validate", 10, "sha123")
    id2 = ForgeQdrantClient.generate_point_id("repo_1", "src/auth.py", "validate", 10, "sha123")
    id3 = ForgeQdrantClient.generate_point_id("repo_1", "src/auth.py", "validate", 11, "sha123")

    assert id1 == id2
    assert id1 != id3
    assert len(id1) == 36  # Standard UUID string format


def test_qdrant_point_upsert_and_search(memory_qdrant: ForgeQdrantClient):
    """Verify real point upsert and payload filtering vector search."""
    points = [
        {
            "file_path": "src/auth.py",
            "language": "python",
            "symbol": "AuthService",
            "symbol_type": "class",
            "start_line": 5,
            "end_line": 25,
            "chunk_hash": "hash_auth",
            "snippet": "class AuthService: def validate_token(self, token): return True",
        },
        {
            "file_path": "src/user.py",
            "language": "python",
            "symbol": "UserService",
            "symbol_type": "class",
            "start_line": 1,
            "end_line": 15,
            "chunk_hash": "hash_user",
            "snippet": "class UserService: def get_user(self, user_id): return {}",
        },
        {
            "file_path": "src/app.ts",
            "language": "typescript",
            "symbol": "AppRouter",
            "symbol_type": "class",
            "start_line": 1,
            "end_line": 30,
            "chunk_hash": "hash_ts",
            "snippet": "export class AppRouter { route() {} }",
        },
    ]

    count = memory_qdrant.upsert_points(repository_id="repo_qdrant_test", points=points)
    assert count == 3

    # Vector search for AuthService
    q_vec = CodeVectorEncoder.encode("AuthService validate_token")
    matches = memory_qdrant.search(query_vector=q_vec, repository_id="repo_qdrant_test", limit=5)

    assert len(matches) == 3
    assert matches[0]["file_path"] in ["src/auth.py", "src/user.py", "src/app.ts"]
    assert "score" in matches[0]

    # Filtered search by language
    py_matches = memory_qdrant.search(
        query_vector=q_vec,
        repository_id="repo_qdrant_test",
        limit=5,
        language="python",
    )
    assert all(m["language"] == "python" for m in py_matches)
    assert len(py_matches) == 2

    # Filtered search by symbol_type
    class_matches = memory_qdrant.search(
        query_vector=q_vec,
        repository_id="repo_qdrant_test",
        limit=5,
        symbol_type="class",
    )
    assert len(class_matches) == 3


def test_qdrant_point_deletion(memory_qdrant: ForgeQdrantClient):
    """Verify deleting file points and clearing repository points."""
    points = [
        {"file_path": "a.py", "language": "python", "snippet": "a"},
        {"file_path": "b.py", "language": "python", "snippet": "b"},
    ]
    memory_qdrant.upsert_points("repo_del", points)

    # Delete specific file
    memory_qdrant.delete_file_points(repository_id="repo_del", file_path="a.py")
    res1 = memory_qdrant.search(query_vector=[0.1] * 384, repository_id="repo_del", limit=5)
    assert len(res1) == 1
    assert res1[0]["file_path"] == "b.py"

    # Clear entire repository
    memory_qdrant.clear_repository_points("repo_del")
    res2 = memory_qdrant.search(query_vector=[0.1] * 384, repository_id="repo_del", limit=5)
    assert len(res2) == 0


def test_qdrant_health_check(memory_qdrant: ForgeQdrantClient):
    """Verify health check returns healthy status when Qdrant is connected."""
    health = memory_qdrant.check_health()
    assert health["status"] == "healthy"
    assert health["qdrant_connected"] is True


def test_qdrant_unreachable_error_handling():
    """Verify Qdrant client handles host connection failures cleanly without fake fallbacks."""
    # Connect to invalid port 59999 where no Qdrant server exists
    offline_client = ForgeQdrantClient(
        collection_name="test_offline",
        host="localhost",
        port=59999,
    )
    health = offline_client.check_health()
    assert health["status"] == "unhealthy"
    assert health["qdrant_connected"] is False

    with pytest.raises(Exception, match=r".*"):
        offline_client.upsert_points("repo_fail", [{"file_path": "f.py", "snippet": "err"}])
