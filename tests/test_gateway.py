from fastapi.testclient import TestClient

from services.gateway.app.api.dependencies.auth import generate_jwt_token
from services.gateway.app.main import app

client = TestClient(app)


def get_auth_headers() -> dict[str, str]:
    token = generate_jwt_token(user_id="user_test_dev", role="admin")
    return {"Authorization": f"Bearer {token}"}


def test_gateway_health_aggregation():
    """Verify GET /health returns aggregated system health status."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "api-gateway"
    assert data["status"] in ["healthy", "degraded", "unhealthy"]


def test_projects_endpoints():
    """Verify /api/v1/projects CRUD routes."""
    headers = get_auth_headers()
    # Create Project
    create_resp = client.post(
        "/api/v1/projects",
        headers=headers,
        json={"name": "Auth Engine", "path": "E:/Repos/auth", "description": "Authentication microservice"},
    )
    assert create_resp.status_code == 201
    assert create_resp.json()["success"] is True
    assert "data" in create_resp.json()

    # List Projects
    list_resp = client.get("/api/v1/projects", headers=headers)
    assert list_resp.status_code == 200
    assert list_resp.json()["success"] is True

    # Get Project
    get_resp = client.get("/api/v1/projects/proj_123", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["data"]["id"] == "proj_123"

    # Delete Project
    del_resp = client.delete("/api/v1/projects/proj_123", headers=headers)
    assert del_resp.status_code == 200
    assert del_resp.json()["data"]["deleted_id"] == "proj_123"


def test_repositories_endpoints():
    """Verify /api/v1/repositories endpoints."""
    headers = get_auth_headers()
    # Open Repo
    open_resp = client.post("/api/v1/repositories/open", headers=headers, json={"path": "E:/Repos/sample"})
    assert open_resp.status_code == 200
    assert open_resp.json()["success"] is True

    # Clone Repo
    clone_resp = client.post("/api/v1/repositories/clone", headers=headers, json={"url": "https://github.com/test/repo.git"})
    assert clone_resp.status_code in (201, 202)

    # Index Repo
    index_resp = client.post("/api/v1/repositories/repo_1/index", headers=headers, json={"force_reindex": True})
    assert index_resp.status_code == 200

    # Get Tree
    tree_resp = client.get("/api/v1/repositories/repo_1/tree", headers=headers)
    assert tree_resp.status_code == 200

    # Get Status
    status_resp = client.get("/api/v1/repositories/repo_1/status", headers=headers)
    assert status_resp.status_code == 200


def test_agent_endpoints():
    """Verify /api/v1/agent endpoints and SSE stream scaffold."""
    headers = get_auth_headers()
    # Create Run
    run_payload = {
        "project_id": "proj_1",
        "mode": "CODE",
        "instruction": "Add JWT validation function",
    }
    create_resp = client.post("/api/v1/agent/runs", headers=headers, json=run_payload)
    assert create_resp.status_code in (201, 202)
    assert create_resp.json()["data"]["mode"] == "CODE"

    # Get Run Status
    get_resp = client.get("/api/v1/agent/runs/run_1", headers=headers)
    assert get_resp.status_code == 200

    # Continue Run
    cont_resp = client.post("/api/v1/agent/runs/run_1/continue", headers=headers, json={"user_feedback": "Approved"})
    assert cont_resp.status_code == 200

    # Cancel Run
    cancel_resp = client.post("/api/v1/agent/runs/run_1/cancel", headers=headers)
    assert cancel_resp.status_code == 200

    # Get Steps
    steps_resp = client.get("/api/v1/agent/runs/run_1/steps", headers=headers)
    assert steps_resp.status_code == 200

    # SSE Stream
    stream_resp = client.get("/api/v1/agent/runs/run_1/stream", headers=headers)
    assert stream_resp.status_code == 200
    assert "text/event-stream" in stream_resp.headers["content-type"]
    assert "event: agent.started" in stream_resp.text


def test_models_endpoints():
    """Verify /api/v1/models endpoints."""
    headers = get_auth_headers()
    # List Models
    list_resp = client.get("/api/v1/models", headers=headers)
    assert list_resp.status_code == 200

    # Select Model
    select_resp = client.post("/api/v1/models/select", headers=headers, json={"model_id": "qwen2.5-coder:7b-instruct-q4_0"})
    assert select_resp.status_code == 200
    assert select_resp.json()["data"]["active_model"] == "qwen2.5-coder:7b-instruct-q4_0"

    # Model Health
    health_resp = client.get("/api/v1/models/health", headers=headers)
    assert health_resp.status_code == 200

    # Benchmark Report
    bench_resp = client.get("/api/v1/models/benchmark", headers=headers)
    assert bench_resp.status_code == 200


def test_git_endpoints():
    """Verify /api/v1/git endpoints."""
    headers = get_auth_headers()
    # Git Status
    status_resp = client.get("/api/v1/git/status", headers=headers)
    assert status_resp.status_code == 200

    # Git Diff
    diff_resp = client.get("/api/v1/git/diff", headers=headers)
    assert diff_resp.status_code == 200

    # Git Log
    log_resp = client.get("/api/v1/git/log", headers=headers)
    assert log_resp.status_code == 200

    # Create Branch
    branch_resp = client.post("/api/v1/git/branches", headers=headers, json={"branch_name": "feature/test"})
    assert branch_resp.status_code in (200, 201, 400, 409)

    # Commit
    commit_resp = client.post("/api/v1/git/commit", headers=headers, json={"message": "test commit"})
    assert commit_resp.status_code in (200, 201, 400)

    # Restore
    restore_resp = client.post("/api/v1/git/restore", headers=headers, json={"files": ["main.py"]})
    assert restore_resp.status_code in (200, 201, 400)


def test_search_endpoints():
    """Verify /api/v1/search endpoints."""
    headers = get_auth_headers()
    # Code Search
    code_resp = client.post("/api/v1/search/code", headers=headers, json={"project_id": "proj_1", "query": "import jwt"})
    assert code_resp.status_code in (200, 201, 404)

    # Semantic Search
    sem_resp = client.post("/api/v1/search/semantic", headers=headers, json={"project_id": "proj_1", "query": "token validation"})
    assert sem_resp.status_code in (200, 201)

    # Symbol Search
    sym_resp = client.post("/api/v1/search/symbol", headers=headers, json={"project_id": "proj_1", "symbol_name": "validate_token"})
    assert sym_resp.status_code in (200, 201)


def test_websocket_endpoint():
    """Verify /api/v1/ws/agent/{run_id} WebSocket connection."""
    with client.websocket_connect("/api/v1/ws/agent/run_100") as websocket:
        data = websocket.receive_json()
        assert data["event"] == "connected"
        assert data["run_id"] == "run_100"

        websocket.send_text("ping_client")
        ack = websocket.receive_json()
        assert ack["event"] == "ack"
        assert ack["received"] == "ping_client"
