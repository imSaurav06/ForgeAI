import tempfile
import uuid
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from services.gateway.app.api.dependencies.auth import generate_jwt_token
from services.gateway.app.main import app

ws_client = TestClient(app)


def get_auth_headers() -> dict[str, str]:
    token = generate_jwt_token(user_id="user_test_dev", role="admin")
    return {"Authorization": f"Bearer {token}"}


def get_client() -> httpx.Client:
    return httpx.Client(base_url="http://127.0.0.1:8000", headers=get_auth_headers(), timeout=30.0)


@pytest.fixture(scope="module")
def sample_repo_path():
    temp_dir = tempfile.mkdtemp(prefix="forge_gw_test_")
    test_path = Path(temp_dir).resolve()
    (test_path / "main.py").write_text("import sys\n\ndef app_entry():\n    return 'OK'\n", encoding="utf-8")
    (test_path / "utils.py").write_text("def helper():\n    return 42\n", encoding="utf-8")
    repo_root = str(test_path).replace("\\", "/")
    yield repo_root
    import shutil
    shutil.rmtree(test_path, ignore_errors=True)


def test_gateway_health_aggregation():
    """Verify GET /health returns aggregated system health status."""
    with get_client() as client:
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "api-gateway"
        assert data["status"] in ["healthy", "degraded", "unhealthy"]


def test_projects_endpoints(sample_repo_path: str):
    """Verify /api/v1/projects CRUD routes."""
    with get_client() as client:
        # Create Project
        create_resp = client.post(
            "/api/v1/projects",
            json={"name": f"Auth Engine {uuid.uuid4().hex[:6]}", "path": sample_repo_path, "description": "Authentication microservice"},
        )
        assert create_resp.status_code == 201
        assert create_resp.json()["success"] is True
        proj_id = create_resp.json()["data"]["id"]

        # List Projects
        list_resp = client.get("/api/v1/projects")
        assert list_resp.status_code == 200
        assert list_resp.json()["success"] is True

        # Get Project
        get_resp = client.get(f"/api/v1/projects/{proj_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["data"]["id"] == proj_id

        # Delete Project
        del_resp = client.delete(f"/api/v1/projects/{proj_id}")
        assert del_resp.status_code == 200
        assert del_resp.json()["data"]["deleted_id"] == proj_id


def test_repositories_endpoints(sample_repo_path: str):
    """Verify /api/v1/repositories endpoints."""
    with get_client() as client:
        # Open Repo
        open_resp = client.post("/api/v1/repositories/open", json={"path": sample_repo_path})
        assert open_resp.status_code == 200
        assert open_resp.json()["success"] is True
        repo_id = open_resp.json()["data"]["id"]

        # Index Repo
        index_resp = client.post(f"/api/v1/repositories/{repo_id}/index", json={"force_reindex": True})
        assert index_resp.status_code in (200, 202)

        # Get Tree
        tree_resp = client.get(f"/api/v1/repositories/{repo_id}/tree")
        assert tree_resp.status_code == 200

        # Get Status
        status_resp = client.get(f"/api/v1/repositories/{repo_id}/status")
        assert status_resp.status_code == 200


def test_conversations_endpoints():
    """Verify /api/v1/conversations multi-turn chat persistence."""
    with get_client() as client:
        # Create Conversation
        create_resp = client.post(
            "/api/v1/conversations",
            json={"title": "Test Chat Session"},
        )
        assert create_resp.status_code == 201
        conv_data = create_resp.json()["data"]
        conv_id = conv_data["id"]
        assert conv_data["title"] == "Test Chat Session"

        # List Conversations
        list_resp = client.get("/api/v1/conversations")
        assert list_resp.status_code == 200
        assert any(c["id"] == conv_id for c in list_resp.json()["data"])

        # Post Message
        msg_resp = client.post(
            f"/api/v1/conversations/{conv_id}/messages",
            json={"content": "How do I implement JWT auth in FastAPI?", "role": "user"},
        )
        assert msg_resp.status_code == 201
        msg_data = msg_resp.json()["data"]
        assert msg_data["conversation_id"] == conv_id
        assert msg_data["content"] == "How do I implement JWT auth in FastAPI?"

        # Get Conversation Details with Messages
        get_resp = client.get(f"/api/v1/conversations/{conv_id}")
        assert get_resp.status_code == 200
        detail = get_resp.json()["data"]
        assert len(detail["messages"]) == 1
        assert detail["messages"][0]["content"] == "How do I implement JWT auth in FastAPI?"


def test_agent_endpoints(sample_repo_path: str):
    """Verify /api/v1/agent endpoints and SSE stream scaffold."""
    with get_client() as client:
        open_resp = client.post("/api/v1/repositories/open", json={"path": sample_repo_path})
        repo_id = open_resp.json()["data"]["id"]

        # Create Run
        run_payload = {
            "project_id": "proj_1",
            "repository_id": repo_id,
            "mode": "PLAN",
            "instruction": "Add JWT validation function",
        }
        create_resp = client.post("/api/v1/agent/runs", json=run_payload)
        assert create_resp.status_code in (201, 202)
        run_id = create_resp.json()["data"]["run_id"]

        # Get Run Status
        get_resp = client.get(f"/api/v1/agent/runs/{run_id}")
        assert get_resp.status_code == 200

        # Continue Run
        cont_resp = client.post(f"/api/v1/agent/runs/{run_id}/continue", json={"user_feedback": "Approved"})
        assert cont_resp.status_code == 200

        # Cancel Run
        cancel_resp = client.post(f"/api/v1/agent/runs/{run_id}/cancel")
        assert cancel_resp.status_code == 200

        # Get Steps
        steps_resp = client.get(f"/api/v1/agent/runs/{run_id}/steps")
        assert steps_resp.status_code == 200


def test_models_endpoints():
    """Verify /api/v1/models endpoints."""
    with get_client() as client:
        # List Models
        list_resp = client.get("/api/v1/models")
        assert list_resp.status_code == 200

        # Select Model
        select_resp = client.post("/api/v1/models/select", json={"model_id": "qwen2.5-coder:7b-instruct-q4_0"})
        assert select_resp.status_code == 200
        assert select_resp.json()["data"]["active_model"] == "qwen2.5-coder:7b-instruct-q4_0"

        # Model Health
        health_resp = client.get("/api/v1/models/health")
        assert health_resp.status_code == 200

        # Benchmark Report
        bench_resp = client.get("/api/v1/models/benchmark")
        assert bench_resp.status_code == 200


def test_git_endpoints():
    """Verify /api/v1/git endpoints."""
    with get_client() as client:
        # Git Status
        status_resp = client.get("/api/v1/git/status")
        assert status_resp.status_code == 200

        # Git Diff
        diff_resp = client.get("/api/v1/git/diff")
        assert diff_resp.status_code == 200

        # Git Log
        log_resp = client.get("/api/v1/git/log")
        assert log_resp.status_code == 200

        # Create Branch
        branch_name = f"feature/gw-test-{uuid.uuid4().hex[:8]}"
        branch_resp = client.post("/api/v1/git/branches", json={"branch_name": branch_name})
        assert branch_resp.status_code in (200, 201, 400, 409)

        # Commit
        commit_resp = client.post("/api/v1/git/commit", json={"message": "test commit"})
        assert commit_resp.status_code in (200, 201, 400, 422)

        # Restore
        restore_resp = client.post("/api/v1/git/restore", json={"files": ["main.py"]})
        assert restore_resp.status_code in (200, 201, 400, 422)


def test_search_endpoints(sample_repo_path: str):
    """Verify /api/v1/search endpoints."""
    with get_client() as client:
        open_resp = client.post("/api/v1/repositories/open", json={"path": sample_repo_path})
        repo_id = open_resp.json()["data"]["id"]

        # Code Search
        code_resp = client.post("/api/v1/search/code", json={"repository_id": repo_id, "query": "import jwt"})
        assert code_resp.status_code in (200, 201)

        # Semantic Search
        sem_resp = client.post("/api/v1/search/semantic", json={"repository_id": repo_id, "query": "token validation"})
        assert sem_resp.status_code in (200, 201)

        # Symbol Search
        sym_resp = client.post("/api/v1/search/symbol", json={"repository_id": repo_id, "symbol_name": "validate_token"})
        assert sym_resp.status_code in (200, 201)


def test_websocket_endpoint():
    """Verify /api/v1/ws/agent/{run_id} WebSocket connection."""
    token = generate_jwt_token(user_id="user_test_dev", role="admin")
    with ws_client.websocket_connect(f"/api/v1/ws/agent/run_100?token={token}") as websocket:
        data = websocket.receive_json()
        assert data["event"] == "connected"
        assert data["run_id"] == "run_100"

        websocket.send_text("ping_client")
        ack = websocket.receive_json()
        assert ack["event"] == "ack"
        assert ack["received"] == "ping_client"
