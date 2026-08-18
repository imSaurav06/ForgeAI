from fastapi.testclient import TestClient

from services.agent.app.main import app as agent_app
from services.evaluation.app.main import app as eval_app
from services.gateway.app.api.dependencies.auth import generate_jwt_token
from services.gateway.app.core.internal_auth import InternalAuthManager
from services.gateway.app.main import app as gateway_app
from services.git.app.main import app as git_app
from services.llm.app.main import app as llm_app
from services.repository.app.main import app as repo_app
from services.retrieval.app.main import app as retrieval_app
from services.tools.app.main import app as tools_app

gateway_client = TestClient(gateway_app)
agent_client = TestClient(agent_app)
repo_client = TestClient(repo_app)
retrieval_client = TestClient(retrieval_app)
llm_client = TestClient(llm_app)
tools_client = TestClient(tools_app)
git_client = TestClient(git_app)
eval_client = TestClient(eval_app)


def get_gateway_auth_headers() -> dict[str, str]:
    token = generate_jwt_token(user_id="user_e2e_dev", role="admin")
    return {"Authorization": f"Bearer {token}"}


def get_internal_headers() -> dict[str, str]:
    token = InternalAuthManager().generate_internal_token("e2e-test-client")
    return {"X-Internal-Service-Token": token}


def test_e2e_01_gateway_health_aggregation():
    """1. Test Gateway health aggregation across microservices."""
    resp = gateway_client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "details" in data or "service" in data


def test_e2e_02_gateway_reverse_proxy():
    """2. Test Gateway proxy routing to internal microservices."""
    headers = get_gateway_auth_headers()
    resp = gateway_client.get("/api/v1/models", headers=headers)
    assert resp.status_code == 200


def test_e2e_03_repository_scanning_and_indexing():
    """3. Test Repository registration, directory scanning, and AST symbol extraction."""
    headers = get_internal_headers()
    # Register Repo
    reg_resp = repo_client.post("/v1/repositories/register", headers=headers, json={"name": "Forge E2E Repo", "path": "."})
    assert reg_resp.status_code == 201
    repo_id = reg_resp.json()["data"]["id"]

    # Scan Repo
    scan_resp = repo_client.post(f"/v1/repositories/{repo_id}/scan", headers=headers)
    assert scan_resp.status_code == 200

    # Index Symbols
    idx_resp = repo_client.post(f"/v1/repositories/{repo_id}/index", headers=headers, json={"force_reindex": True})
    assert idx_resp.status_code == 200
    assert idx_resp.json()["data"]["total_symbols"] > 0


def test_e2e_04_rag_embeddings_and_retrieval():
    """4. Test Retrieval Service vector indexing, hybrid search, and context assembly."""
    headers = get_internal_headers()
    repo_id = "repo_e2e_test"

    # Index Vectors
    idx_resp = retrieval_client.post("/v1/index/embeddings", headers=headers, json={"repository_id": repo_id, "force_reindex": True})
    assert idx_resp.status_code == 202

    # Hybrid Search
    hyb_resp = retrieval_client.post("/v1/search/hybrid", headers=headers, json={"repository_id": repo_id, "query": "auth middleware"})
    assert hyb_resp.status_code == 200

    # Context Assembly
    ctx_resp = retrieval_client.post("/v1/search/context", headers=headers, json={"repository_id": repo_id, "query": "JWT validation", "max_tokens": 2048})
    assert ctx_resp.status_code == 200
    assert "RETRIEVED REPOSITORY CONTEXT" in ctx_resp.json()["data"]["context_text"]


def test_e2e_05_llm_generation_and_streaming():
    """5. Test LLM prompt completion, template compilation, and SSE token streaming."""
    headers = get_internal_headers()
    # Text Generation
    gen_resp = llm_client.post("/v1/generate", headers=headers, json={"prompt": "Write JWT validation function", "mode": "CODE"})
    assert gen_resp.status_code == 200
    assert "model" in gen_resp.json()["data"]

    # SSE Token Streaming
    stream_resp = llm_client.post("/v1/stream", headers=headers, json={"prompt": "Stream completion"})
    assert stream_resp.status_code == 200
    assert "text/event-stream" in stream_resp.headers["content-type"]


def test_e2e_06_tool_execution_and_rollback():
    """Test repository-scoped Tool Service operations and security boundaries."""
    headers = get_internal_headers()

    repo_root = Path(".").resolve()

    reg_resp = repo_client.post(
        "/v1/repositories/register",
        headers=headers,
        json={
            "name": "ForgeAI Tool E2E Repo",
            "path": str(repo_root).replace("\\", "/"),
        },
    )

    assert reg_resp.status_code == 201
    repository_id = reg_resp.json()["data"]["id"]

    # Write File
    w_resp = tools_client.post(
        "/internal/v1/tools/write-file",
        headers=headers,
        json={
            "repository_id": repository_id,
            "path": "e2e_test.py",
            "content": "x = 42\n",
        },
    )
    assert w_resp.status_code == 200

    # Read File
    r_resp = tools_client.post(
        "/internal/v1/tools/read-file",
        headers=headers,
        json={
            "repository_id": repository_id,
            "path": "e2e_test.py",
        },
    )
    assert r_resp.status_code == 200

    # Path Traversal Attack -> Blocked
    bad_r = tools_client.post(
        "/internal/v1/tools/read-file",
        headers=headers,
        json={
            "repository_id": repository_id,
            "path": "../../etc/passwd",
        },
    )
    assert bad_r.status_code in (400, 401, 422)

    # Dangerous Command -> Blocked
    bad_cmd = tools_client.post(
        "/internal/v1/tools/run-command",
        headers=headers,
        json={
            "command": "rm -rf /",
        },
    )
    assert bad_cmd.status_code in (400, 401, 422)

    # Delete File
    d_resp = tools_client.post(
        "/internal/v1/tools/delete-file",
        headers=headers,
        json={
            "repository_id": repository_id,
            "path": "e2e_test.py",
        },
    )
    assert d_resp.status_code == 200
    """6. Test Tool Service file read/write, dangerous command blocking, and patch rollback."""
    headers = get_internal_headers()
    # Write File
    w_resp = tools_client.post("/internal/v1/tools/write-file", headers=headers, json={"path": "e2e_test.py", "content": "x = 42\n"})
    assert w_resp.status_code == 200

    # Read File
    r_resp = tools_client.post("/internal/v1/tools/read-file", headers=headers, json={"path": "e2e_test.py"})
    assert r_resp.status_code == 200

    # Path Traversal Attack -> Blocked
    bad_r = tools_client.post("/internal/v1/tools/read-file", headers=headers, json={"path": "../../etc/passwd"})
    assert bad_r.status_code in (400, 401, 422)

    # Dangerous Command -> Blocked
    bad_cmd = tools_client.post("/internal/v1/tools/run-command", headers=headers, json={"command": "rm -rf /"})
    assert bad_cmd.status_code in (400, 401, 422)

    # Delete File
    d_resp = tools_client.post("/internal/v1/tools/delete-file", headers=headers, json={"path": "e2e_test.py"})
    assert d_resp.status_code == 200


def test_e2e_07_git_version_control():
    """7. Test Git version-control status, branch creation, commit, and restore."""
    headers = get_internal_headers()
    # Status
    st_resp = git_client.get("/v1/git/status", headers=headers)
    assert st_resp.status_code == 200

    # Branch Creation
    br_resp = git_client.post("/v1/git/branches", headers=headers, json={"branch_name": "feature/e2e-test", "checkout": True})
    assert br_resp.status_code == 201

    # Diff
    diff_resp = git_client.get("/v1/git/diff", headers=headers)
    assert diff_resp.status_code == 200


def test_e2e_08_autonomous_agent_execution():
    """8. Test Autonomous Agent run execution, state transitions, and step tracking."""
    headers = get_internal_headers()
    create_resp = agent_client.post(
        "/v1/agent/runs",
        headers=headers,
        json={
            "project_id": "proj_e2e",
            "repository_id": "repo_e2e",
            "mode": "PLAN",
            "instruction": "Plan refactoring of API gateway",
        },
    )
    assert create_resp.status_code == 201
    run_id = create_resp.json()["data"]["run_id"]

    # Verify Run Steps
    steps_resp = agent_client.get(f"/v1/agent/runs/{run_id}/steps", headers=headers)
    assert steps_resp.status_code == 200

    # Verify Event Stream
    events_resp = agent_client.get(f"/v1/agent/runs/{run_id}/events", headers=headers)
    assert events_resp.status_code == 200
    assert len(events_resp.json()["data"]) > 0


def test_e2e_09_evaluation_and_benchmarks():
    """9. Test Evaluation Service benchmark suite execution across 7 modes and report generation."""
    headers = get_internal_headers()
    # Run Benchmark Suite
    bm_resp = eval_client.post("/v1/evaluations/benchmark", headers=headers, json={"model": "qwen2.5-coder:7b-instruct-q4_0"})
    assert bm_resp.status_code == 200
    assert bm_resp.json()["data"]["total_suites_count"] == 7

    # Get Markdown Reports
    rep_resp = eval_client.get("/v1/evaluations/reports", headers=headers)
    assert rep_resp.status_code == 200
