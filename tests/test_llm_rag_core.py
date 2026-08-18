import pytest
from fastapi.testclient import TestClient

from services.llm.app.adapters.ollama_adapter import OllamaAdapter
from services.llm.app.main import app as llm_app
from services.llm.app.prompts.templates import PromptTemplateRegistry
from services.llm.app.services.llm_service import LLMService
from services.retrieval.app.context.context_builder import ContextBuilder
from services.retrieval.app.embeddings.vector_encoder import CodeVectorEncoder
from services.retrieval.app.main import app as retrieval_app
from services.retrieval.app.qdrant.qdrant_client import ForgeQdrantClient
from services.retrieval.app.reranking.reranker import CodeRRFReranker
from services.retrieval.app.search.pipeline import RAGSearchPipeline

llm_client = TestClient(llm_app)
retrieval_client = TestClient(retrieval_app)


@pytest.mark.asyncio
async def test_ollama_adapter():
    """Verify Ollama adapter health check and completion fallback."""
    adapter = OllamaAdapter()
    health = await adapter.check_health()
    assert "status" in health
    assert "ollama_connected" in health

    models = await adapter.list_models()
    assert len(models) >= 1

    gen = await adapter.generate(model="qwen2.5-coder:3b-instruct-q4_0", prompt="Write health check")
    assert "response" in gen


def test_prompt_template_registry():
    """Verify system and prompt template compilation across modes."""
    modes = ["ASK", "PLAN", "CODE", "DEBUG", "TEST", "REVIEW", "EXPLAIN"]

    for m in modes:
        sys_p, user_p = PromptTemplateRegistry.compile_prompt(mode=m, instruction="Test instruction", context="Sample context")
        assert len(sys_p) > 0
        assert "Test instruction" in user_p
        assert "Sample context" in user_p


def test_llm_service_model_switching():
    """Verify LLM active model switching."""
    svc = LLMService()
    assert "qwen2.5-coder" in svc.active_model

    svc.select_model("qwen2.5-coder:7b-instruct-q4_0")
    assert svc.active_model == "qwen2.5-coder:7b-instruct-q4_0"

    svc.select_model("qwen2.5-coder:3b-instruct-q4_0")
    assert svc.active_model == "qwen2.5-coder:3b-instruct-q4_0"


def test_vector_encoder():
    """Verify CodeVectorEncoder 384-dim encoding and cosine similarity."""
    vec_a = CodeVectorEncoder.encode("def validate_jwt_token(token: str): pass")
    vec_b = CodeVectorEncoder.encode("def validate_jwt_token(token: str): pass")
    vec_c = CodeVectorEncoder.encode("import os\nos.listdir('.')")

    assert len(vec_a) == 384
    sim_same = CodeVectorEncoder.cosine_similarity(vec_a, vec_b)
    sim_diff = CodeVectorEncoder.cosine_similarity(vec_a, vec_c)

    assert sim_same == pytest.approx(1.0, rel=1e-3)
    assert sim_same >= sim_diff


def test_qdrant_vector_store():
    """Verify ForgeQdrantClient point upserts and similarity search."""
    qdrant = ForgeQdrantClient(collection_name="test_forge_ai_code", location=":memory:")
    points = [
        {
            "file_path": "auth/service.py",
            "language": "python",
            "symbol": "AuthService",
            "symbol_type": "class",
            "snippet": "class AuthService: def validate(self): pass",
        }
    ]
    upserted = qdrant.upsert_points("repo_test_qdrant", points)
    assert upserted == 1

    query_vec = CodeVectorEncoder.encode("AuthService validate")
    matches = qdrant.search(query_vec, repository_id="repo_test_qdrant", limit=5)
    assert len(matches) == 1
    assert matches[0]["file_path"] == "auth/service.py"


def test_rag_search_pipeline_and_reranker():
    """Verify intent analysis, query expansion, and RRF reranking."""
    pipeline = RAGSearchPipeline()
    intent = pipeline.analyze_intent("Fix JWT authentication error")
    assert intent["intent"] == "authentication"

    expansions = pipeline.expand_query("auth")
    assert "jwt" in expansions or "authentication" in expansions

    v_res = [{"file_path": "a.py", "start_line": 1, "symbol": "foo", "snippet": "code a"}]
    s_res = [{"file_path": "b.py", "start_line": 1, "symbol": "bar", "snippet": "code b"}]
    k_res = [{"file_path": "a.py", "start_line": 1, "symbol": "foo", "snippet": "code a"}]

    reranked = CodeRRFReranker.rerank(v_res, s_res, k_res, top_k=2)
    assert len(reranked) >= 1
    assert "rrf_score" in reranked[0]


def test_context_builder_token_budgeting():
    """Verify ContextBuilder token budgeting and truncation."""
    snippets = [
        {"file_path": "service.py", "start_line": 1, "end_line": 20, "symbol": "foo", "snippet": "def foo():\n    return 'ok'\n" * 50},
        {"file_path": "models.py", "start_line": 1, "end_line": 20, "symbol": "bar", "snippet": "class Bar:\n    pass\n" * 50},
    ]

    ctx = ContextBuilder.build_context(snippets, max_token_budget=100)
    assert ctx["total_tokens_used"] <= 120
    assert ctx["snippet_count"] >= 1
    assert "=== RETRIEVED REPOSITORY CONTEXT ===" in ctx["context_text"]


def get_internal_headers() -> dict[str, str]:
    from services.gateway.app.core.internal_auth import InternalAuthManager
    token = InternalAuthManager().generate_internal_token("test-client")
    return {"X-Internal-Service-Token": token}


def test_llm_api_endpoints():
    """Verify LLM Service API endpoints."""
    headers = get_internal_headers()
    # Generate
    gen_resp = llm_client.post("/v1/generate", headers=headers, json={"prompt": "Create JWT auth function", "mode": "CODE"})
    assert gen_resp.status_code == 200
    assert gen_resp.json()["data"]["model"] is not None

    # Chat
    chat_resp = llm_client.post("/v1/chat", headers=headers, json={"messages": [{"role": "user", "content": "Hello"}]})
    assert chat_resp.status_code == 200

    # Stream
    stream_resp = llm_client.post("/v1/stream", headers=headers, json={"prompt": "Stream code"})
    assert stream_resp.status_code == 200
    assert "text/event-stream" in stream_resp.headers["content-type"]

    # Models List
    models_resp = llm_client.get("/v1/models", headers=headers)
    assert models_resp.status_code == 200

    # Select Model
    sel_resp = llm_client.post("/v1/models/select", headers=headers, json={"model_id": "qwen2.5-coder:3b-instruct-q4_0"})
    assert sel_resp.status_code == 200
    assert sel_resp.json()["data"]["active_model"] == "qwen2.5-coder:3b-instruct-q4_0"

    # Health
    health_resp = llm_client.get("/v1/models/health", headers=headers)
    assert health_resp.status_code == 200


def test_retrieval_api_endpoints():
    """Verify Retrieval Service API endpoints."""
    headers = get_internal_headers()
    # Index Embeddings
    idx_resp = retrieval_client.post("/v1/index/embeddings", headers=headers, json={"repository_id": "repo_123", "force_reindex": True})
    assert idx_resp.status_code == 202

    # Semantic Search
    sem_resp = retrieval_client.post("/v1/search/semantic", headers=headers, json={"repository_id": "repo_123", "query": "auth token"})
    assert sem_resp.status_code == 200

    # Hybrid Search
    hyb_resp = retrieval_client.post("/v1/search/hybrid", headers=headers, json={"repository_id": "repo_123", "query": "JWT validation"})
    assert hyb_resp.status_code == 200

    # Context Search
    ctx_resp = retrieval_client.post("/v1/search/context", headers=headers, json={"repository_id": "repo_123", "query": "authentication", "max_tokens": 2048})
    assert ctx_resp.status_code == 200
    assert ctx_resp.json()["data"]["max_token_budget"] == 2048

    # Status
    status_resp = retrieval_client.get("/v1/index/status?repository_id=repo_123", headers=headers)
    assert status_resp.status_code == 200
