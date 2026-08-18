"""
Real Local Semantic Code Embedding Integration Tests.

Validates ONNX BAAI/bge-small-en-v1.5 model loading via FastEmbed,
dense 384-dimensional vector generation, batch encoding, determinism,
semantic ranking quality, real Qdrant vector search integration,
and absence of fake hash fallbacks.
"""

import pytest

from services.retrieval.app.embeddings.vector_encoder import CodeVectorEncoder, get_code_vector_encoder
from services.retrieval.app.qdrant.qdrant_client import ForgeQdrantClient


@pytest.fixture
def encoder() -> CodeVectorEncoder:
    """Fixture returning global CodeVectorEncoder singleton."""
    return get_code_vector_encoder()


def test_real_embedding_model_load_and_dimension(encoder: CodeVectorEncoder):
    """Verify local semantic embedding model loads and reports 384 dimensions."""
    assert encoder.dimension == 384
    health = encoder.check_health()
    assert health["status"] == "healthy"
    assert health["dimension"] == 384
    assert "bge-small-en" in health["model_name"]


def test_single_text_embedding(encoder: CodeVectorEncoder):
    """Verify single text input produces a dense float vector of length 384."""
    text = "def validate_jwt_token(token: str) -> bool: return True"
    vec = encoder.encode(text)

    assert isinstance(vec, list)
    assert len(vec) == 384
    assert all(isinstance(v, float) for v in vec)
    # Verify non-trivial dense continuous float values
    assert any(abs(v) > 0.001 for v in vec)


def test_batch_embedding(encoder: CodeVectorEncoder):
    """Verify batch embedding produces list of dense float vectors matching input batch size."""
    texts = [
        "Language: Python\nFile: auth/jwt.py\nSymbol: validate_token",
        "Language: Python\nFile: db/pool.py\nSymbol: get_connection",
        "Language: TypeScript\nFile: src/app.ts\nSymbol: renderApp",
    ]
    vectors = encoder.encode_batch(texts)

    assert len(vectors) == 3
    assert all(len(v) == 384 for v in vectors)


def test_embedding_determinism_and_differentiation(encoder: CodeVectorEncoder):
    """Verify identical text produces identical vectors while different texts produce different vectors."""
    text_a = "def process_payment(amount: float): pass"
    text_b = "class UserDatabaseManager: pass"

    vec_a1 = encoder.encode(text_a)
    vec_a2 = encoder.encode(text_a)
    vec_b = encoder.encode(text_b)

    # Identical inputs produce identical vectors
    sim_identical = CodeVectorEncoder.cosine_similarity(vec_a1, vec_a2)
    assert sim_identical >= 0.9999

    # Different semantic inputs produce distinct vectors
    sim_different = CodeVectorEncoder.cosine_similarity(vec_a1, vec_b)
    assert sim_different < 0.95
    assert vec_a1 != vec_b


def test_semantic_ranking_quality(encoder: CodeVectorEncoder):
    """
    SEMANTIC QUALITY TEST: Verify query 'Fix expired authentication tokens'
    ranks Auth JWT symbol above Database Pool symbol.
    """
    doc_auth = (
        "Language: Python\n"
        "File: services/auth/jwt_verifier.py\n"
        "Symbol: verify_token_expiration\n"
        "Type: function\n"
        "Signature: verify_token_expiration(token: str) -> None\n"
        "Code:\n"
        "def verify_token_expiration(token: str):\n"
        "    payload = jwt.decode(token, secret)\n"
        "    if payload.get('exp') < time.time():\n"
        "        raise TokenExpiredException('JWT token has expired')\n"
    )

    doc_db = (
        "Language: Python\n"
        "File: services/database/pool.py\n"
        "Symbol: get_postgres_connection\n"
        "Type: function\n"
        "Signature: get_postgres_connection() -> Connection\n"
        "Code:\n"
        "def get_postgres_connection():\n"
        "    return psycopg2.connect(dsn='postgresql://localhost/db')\n"
    )

    query = "Fix expired authentication tokens"

    vecs = encoder.encode_batch([query, doc_auth, doc_db])
    q_vec, auth_vec, db_vec = vecs[0], vecs[1], vecs[2]

    score_auth = CodeVectorEncoder.cosine_similarity(q_vec, auth_vec)
    score_db = CodeVectorEncoder.cosine_similarity(q_vec, db_vec)

    assert score_auth > score_db, (
        f"Semantic quality failure: Auth doc score ({score_auth:.4f}) must be higher than DB doc score ({score_db:.4f})"
    )


def test_real_qdrant_and_real_embeddings_integration():
    """
    E2E REAL QDRANT + REAL EMBEDDINGS INTEGRATION TEST:
    Embed real code -> Upsert to real Qdrant -> Execute real vector query -> Verify ranking.
    """
    qdrant = ForgeQdrantClient(location=":memory:")
    encoder = get_code_vector_encoder()

    repo_id = "repo_real_emb_e2e"

    snippet_auth = "File: auth/jwt.py\nSymbol: validate_jwt\nSnippet: decode token and verify exp claim"
    snippet_math = "File: math/calculator.py\nSymbol: calculate_prime\nSnippet: sieve of eratosthenes prime numbers"

    vec_auth = encoder.encode(snippet_auth)
    vec_math = encoder.encode(snippet_math)

    points = [
        {
            "file_path": "auth/jwt.py",
            "language": "python",
            "symbol": "validate_jwt",
            "symbol_type": "function",
            "start_line": 10,
            "end_line": 25,
            "chunk_hash": "hash_auth",
            "snippet": snippet_auth,
            "embedding": vec_auth,
        },
        {
            "file_path": "math/calculator.py",
            "language": "python",
            "symbol": "calculate_prime",
            "symbol_type": "function",
            "start_line": 1,
            "end_line": 15,
            "chunk_hash": "hash_math",
            "snippet": snippet_math,
            "embedding": vec_math,
        },
    ]

    # Upsert points
    qdrant.upsert_points(repository_id=repo_id, points=points)

    # Execute search for auth query
    q_vec = encoder.encode("authentication token expired verification")
    results = qdrant.search(query_vector=q_vec, repository_id=repo_id, limit=2)

    assert len(results) >= 1
    top_match = results[0]
    assert top_match["file_path"] == "auth/jwt.py"
    assert top_match["symbol"] == "validate_jwt"
