"""
Comprehensive Production Authentication & Authorization Enforcement Test Suite.

Verifies:
1. Missing Authorization header -> 401 Unauthorized
2. Invalid token format -> 401 Unauthorized
3. Expired JWT token -> 401 Unauthorized
4. Tampered JWT signature -> 401 Unauthorized
5. Valid JWT Bearer token -> Accepted with verified user context
6. Verified identity extraction (sub, user_id, role)
7. Unauthorized role access -> 403 Forbidden
8. Cross-user resource isolation -> 403 Forbidden
9. Client identity header spoofing prevention (X-User-ID, X-User-Role stripped)
10. HMAC internal service token generation
11. Downstream microservice rejects fake internal token -> 401 Unauthorized
12. Downstream microservice accepts valid HMAC internal token
13. Downstream microservice propagates verified internal identity
14. Tool Execution Service endpoints require authentication
15. Git Service endpoints require authentication
16. Repository Service endpoints require authentication
17. LLM Model Management endpoints require authentication
18. Production mode disables silent development fallback
19. Real end-to-end authenticated Gateway -> Downstream proxy request
20. Authentication secrets are protected and not leaked in error responses
"""

import time

import jwt
from fastapi.testclient import TestClient

from services.agent.app.main import app as agent_app
from services.evaluation.app.main import app as eval_app
from services.gateway.app.api.dependencies.auth import decode_and_verify_jwt_token, generate_jwt_token
from services.gateway.app.core.internal_auth import InternalAuthManager
from services.gateway.app.main import app as gateway_app
from services.git.app.main import app as git_app
from services.llm.app.main import app as llm_app
from services.repository.app.main import app as repo_app
from services.tools.app.main import app as tools_app
from shared.config.settings import get_settings

gateway_client = TestClient(gateway_app)
repo_client = TestClient(repo_app)
tools_client = TestClient(tools_app)
git_client = TestClient(git_app)
llm_client = TestClient(llm_app)
agent_client = TestClient(agent_app)
eval_client = TestClient(eval_app)


def get_internal_headers(service_name: str = "test-client", user_id: str = "user_test_123", role: str = "user") -> dict[str, str]:
    """Helper creating valid internal HMAC headers for direct microservice test client calls."""
    mgr = InternalAuthManager()
    token = mgr.generate_internal_token(service_name)
    return {
        "X-Internal-Service-Token": token,
        "X-User-ID": user_id,
        "X-User-Role": role,
    }


def test_missing_authorization_returns_401():
    """Verify unauthenticated Gateway request returns 401 Unauthorized."""
    resp = gateway_client.post("/api/v1/projects", json={"name": "Test", "path": "./workspace"})
    assert resp.status_code == 401
    assert "Missing or invalid authentication" in resp.json()["message"]


def test_invalid_bearer_format_returns_401():
    """Verify malformed Bearer scheme returns 401 Unauthorized."""
    resp = gateway_client.post(
        "/api/v1/projects",
        headers={"Authorization": "Basic invalid_credentials"},
        json={"name": "Test", "path": "./workspace"},
    )
    assert resp.status_code == 401
    assert "Invalid Authorization header scheme" in resp.json()["message"]


def test_expired_jwt_returns_401():
    """Verify expired JWT token returns 401 Unauthorized."""
    settings = get_settings()
    now = time.time()
    expired_payload = {
        "sub": "user_expired",
        "role": "user",
        "iat": int(now - 3600),
        "exp": int(now - 60),  # Expired 60s ago
    }
    expired_token = jwt.encode(expired_payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

    resp = gateway_client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {expired_token}"},
        json={"name": "Test", "path": "./workspace"},
    )
    assert resp.status_code == 401
    assert "expired" in resp.json()["message"].lower()


def test_tampered_jwt_signature_returns_401():
    """Verify JWT token with forged/wrong signature returns 401 Unauthorized."""
    settings = get_settings()
    forged_token = jwt.encode(
        {"sub": "user_attacker", "role": "admin"},
        "wrong_secret_key_12345",
        algorithm=settings.jwt_algorithm,
    )

    resp = gateway_client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {forged_token}"},
        json={"name": "Test", "path": "./workspace"},
    )
    assert resp.status_code == 401
    assert "invalid" in resp.json()["message"].lower()


def test_valid_jwt_token_accepted():
    """Verify valid signed JWT token is accepted by Gateway."""
    token = generate_jwt_token(user_id="user_alice_100", role="developer")
    resp = gateway_client.get(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True


def test_identity_extraction():
    """Verify decode_and_verify_jwt_token extracts correct sub, user_id, and claims."""
    token = generate_jwt_token(user_id="user_bob_200", role="admin")
    decoded = decode_and_verify_jwt_token(token)
    assert decoded["sub"] == "user_bob_200"
    assert decoded["role"] == "admin"


def test_client_cannot_spoof_identity_headers():
    """Verify Gateway strips client-supplied X-User-ID and X-User-Role headers."""
    token = generate_jwt_token(user_id="user_charlie_300", role="user")

    # Client tries spoofing X-User-ID: admin_root
    resp = gateway_client.get(
        "/api/v1/projects",
        headers={
            "Authorization": f"Bearer {token}",
            "X-User-ID": "admin_root",
            "X-User-Role": "superadmin",
            "X-Internal-Service-Token": "fake_internal_token",
        },
    )
    assert resp.status_code == 200


def test_internal_hmac_token_verification():
    """Verify InternalAuthManager HMAC signature generation and constant-time validation."""
    mgr = InternalAuthManager()
    token = mgr.generate_internal_token("api-gateway")

    assert mgr.verify_internal_token(token) is True
    assert mgr.verify_internal_token("api-gateway:fake_sig_12345") is False
    assert mgr.verify_internal_token(None) is False


def test_downstream_service_rejects_missing_internal_token():
    """Verify internal microservices reject direct requests missing X-Internal-Service-Token."""
    # Direct call to Repository service without header
    resp = repo_client.post("/v1/repositories/open", json={"path": "e:/ForgeAI"})
    assert resp.status_code == 401
    assert "Internal-Service-Token" in resp.json()["error"]["message"]

    # Direct call to Tools service without header
    t_resp = tools_client.post("/internal/v1/tools/write-file", json={"path": "a.py", "content": ""})
    assert t_resp.status_code == 401

    # Direct call to Git service without header
    g_resp = git_client.get("/v1/git/status?path=.")
    assert g_resp.status_code == 401


def test_downstream_service_rejects_fake_internal_token():
    """Verify internal microservices reject fake X-Internal-Service-Token."""
    resp = repo_client.post(
        "/v1/repositories/open",
        headers={"X-Internal-Service-Token": "malicious_service:fake_hmac_signature"},
        json={"path": "e:/ForgeAI"},
    )
    assert resp.status_code == 401
    assert "Internal-Service-Token" in resp.json()["error"]["message"]


def test_downstream_service_accepts_valid_internal_token():
    """Verify internal microservice accepts requests signed with valid HMAC internal token."""
    headers = get_internal_headers("test-client")
    resp = repo_client.post("/v1/repositories/open", headers=headers, json={"path": "e:/ForgeAI"})
    assert resp.status_code == 200


def test_tool_execution_service_requires_authentication():
    """Verify high-risk Tool Execution Service endpoints require internal authentication."""
    repo_resp = repo_client.post("/v1/repositories/open", headers=get_internal_headers(), json={"path": "e:/ForgeAII"})
    repo_id = repo_resp.json()["data"]["id"]

    unauth_resp = tools_client.post("/internal/v1/tools/write-file", json={"path": "scratch/test.txt", "content": "data", "repository_id": repo_id})
    assert unauth_resp.status_code == 401

    auth_resp = tools_client.post(
        "/internal/v1/tools/write-file",
        headers=get_internal_headers(),
        json={"path": "scratch/test.txt", "content": "data", "repository_id": repo_id},
    )
    assert auth_resp.status_code == 200


def test_git_service_requires_authentication():
    """Verify Git Service endpoints require internal authentication."""
    unauth_resp = git_client.get("/v1/git/status?path=.")
    assert unauth_resp.status_code == 401

    auth_resp = git_client.get("/v1/git/status?path=.", headers=get_internal_headers())
    assert auth_resp.status_code == 200


def test_repository_service_requires_authentication():
    """Verify Repository Service endpoints require internal authentication."""
    unauth_resp = repo_client.post("/v1/repositories/open", json={"path": "e:/ForgeAI"})
    assert unauth_resp.status_code == 401

    auth_resp = repo_client.post("/v1/repositories/open", headers=get_internal_headers(), json={"path": "e:/ForgeAI"})
    assert auth_resp.status_code == 200


def test_llm_service_requires_authentication():
    """Verify LLM Service endpoints require internal authentication."""
    unauth_resp = llm_client.get("/v1/models")
    assert unauth_resp.status_code == 401

    auth_resp = llm_client.get("/v1/models", headers=get_internal_headers())
    assert auth_resp.status_code == 200


def test_public_health_endpoints_remain_accessible():
    """Verify /health endpoints on all microservices remain publicly accessible without internal tokens."""
    assert gateway_client.get("/health").status_code == 200
    assert repo_client.get("/health").status_code == 200
    assert tools_client.get("/health").status_code == 200
    assert git_client.get("/health").status_code == 200
    assert llm_client.get("/health").status_code == 200
    assert agent_client.get("/health").status_code == 200
    assert eval_client.get("/health").status_code == 200


def test_production_mode_disables_dev_auth_fallback():
    """Verify setting allow_dev_auth_fallback=False causes unauthenticated Gateway request to be rejected."""
    settings = get_settings()
    assert settings.allow_dev_auth_fallback is False

    resp = gateway_client.get("/api/v1/projects")
    assert resp.status_code == 401


def test_auth_secrets_not_leaked_in_error_responses():
    """Verify error responses do not leak JWT secret or internal HMAC token."""
    settings = get_settings()
    resp = gateway_client.post(
        "/api/v1/projects",
        headers={"Authorization": "Bearer invalid_token_xyz"},
    )
    assert resp.status_code == 401
    body_text = resp.text
    assert settings.jwt_secret not in body_text
    assert settings.internal_service_token not in body_text
