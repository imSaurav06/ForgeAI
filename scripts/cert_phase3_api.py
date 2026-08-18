"""
Phase 3 API + Swagger 8/8 Forensic Certification Script
Validates OpenAPI docs across all 8 microservices, gateway routes matrix, and security auth negative battery.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

import httpx

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from services.gateway.app.api.dependencies.auth import generate_jwt_token
from services.gateway.app.core.internal_auth import InternalAuthManager

SERVICES = [
    {"name": "Gateway", "port": 8000, "url": "http://localhost:8000"},
    {"name": "Agent", "port": 8001, "url": "http://localhost:8001"},
    {"name": "LLM", "port": 8002, "url": "http://localhost:8002"},
    {"name": "Repository", "port": 8003, "url": "http://localhost:8003"},
    {"name": "Retrieval", "port": 8004, "url": "http://localhost:8004"},
    {"name": "Tools", "port": 8005, "url": "http://localhost:8005"},
    {"name": "Git", "port": 8006, "url": "http://localhost:8006"},
    {"name": "Evaluation", "port": 8007, "url": "http://localhost:8007"},
]


def test_swagger_endpoints() -> dict[str, Any]:
    print("\n[1/3] VERIFYING SWAGGER/OPENAPI ACROSS ALL 8 MICROSERVICES...")
    results = {}
    auth_mgr = InternalAuthManager()

    for svc in SERVICES:
        name = svc["name"]
        url = svc["url"]
        headers = {}
        auth_mgr.inject_internal_headers(headers, user_id="admin_test", user_role="admin")
        
        # Test /openapi.json, /docs, /redoc
        with httpx.Client(timeout=15.0) as client:
            try:
                openapi_res = client.get(f"{url}/openapi.json", headers=headers)
                docs_res = client.get(f"{url}/docs", headers=headers)
                redoc_res = client.get(f"{url}/redoc", headers=headers)

                openapi_ok = openapi_res.status_code == 200 and "openapi" in openapi_res.json()
                docs_ok = docs_res.status_code == 200 and "swagger" in docs_res.text.lower()
                redoc_ok = redoc_res.status_code == 200

                status = "PASS" if (openapi_ok and docs_ok and redoc_ok) else "FAIL"
                endpoint_count = len(openapi_res.json().get("paths", {})) if openapi_ok else 0

                print(f"    [+] {name:12} ({url}): /openapi.json: {openapi_res.status_code}, /docs: {docs_res.status_code}, /redoc: {redoc_res.status_code} | Endpoints: {endpoint_count} -> {status}")
                results[name] = {
                    "openapi_status": openapi_res.status_code,
                    "docs_status": docs_res.status_code,
                    "redoc_status": redoc_res.status_code,
                    "endpoints_count": endpoint_count,
                    "status": status,
                }
                assert status == "PASS", f"Swagger verification failed for {name}"
            except Exception as e:
                print(f"    [!] {name} connection error: {e}")
                results[name] = {"status": "FAIL", "error": str(e)}
                raise

    return results


def test_gateway_api_matrix() -> dict[str, Any]:
    print("\n[2/3] VERIFYING GATEWAY PUBLIC API MATRIX...")
    token = generate_jwt_token(user_id="user_cert_admin", role="admin")
    headers = {"Authorization": f"Bearer {token}"}
    base_url = "http://localhost:8000"

    # Create lightweight test workspace directory
    test_dir = tempfile.mkdtemp(prefix="forge_cert_api_")
    test_path = Path(test_dir).resolve()
    (test_path / "main.py").write_text("import sys\n\ndef app_entry():\n    return 'OK'\n", encoding="utf-8")
    (test_path / "utils.py").write_text("def helper():\n    return 42\n", encoding="utf-8")
    repo_root = str(test_path).replace("\\", "/")

    with httpx.Client(base_url=base_url, timeout=30.0) as client:
        # 1. Projects
        p_res = client.post("/api/v1/projects", headers=headers, json={"name": f"Cert Proj {uuid.uuid4().hex[:6]}", "path": repo_root})
        assert p_res.status_code == 201, f"Projects create failed: {p_res.text}"
        proj_id = p_res.json()["data"]["id"]
        print(f"    [+] Projects API: Created {proj_id}")

        # 2. Repositories
        r_open = client.post("/api/v1/repositories/open", headers=headers, json={"path": repo_root})
        assert r_open.status_code == 200
        repo_id = r_open.json()["data"]["id"]
        print(f"    [+] Repositories API: Opened {repo_id}")

        r_tree = client.get(f"/api/v1/repositories/{repo_id}/tree", headers=headers)
        assert r_tree.status_code == 200
        print(f"    [+] Repositories API: Retrieved Tree for {repo_id}")

        # 3. Chat / Conversations
        c_res = client.post("/api/v1/conversations", headers=headers, json={"title": "Forensic Chat Session"})
        assert c_res.status_code == 201
        conv_id = c_res.json()["data"]["id"]
        msg_res = client.post(f"/api/v1/conversations/{conv_id}/messages", headers=headers, json={"content": "Hello ForgeAI"})
        assert msg_res.status_code == 201
        print(f"    [+] Conversations API: Created {conv_id} and added message")

        # 4. Models
        m_list = client.get("/api/v1/models", headers=headers)
        assert m_list.status_code == 200
        m_sel = client.post("/api/v1/models/select", headers=headers, json={"model_id": "qwen2.5-coder:7b-instruct-q4_0"})
        assert m_sel.status_code == 200
        print(f"    [+] Models API: Model list and select validated")

        # 5. Search
        s_code = client.post("/api/v1/search/code", headers=headers, json={"repository_id": repo_id, "query": "import sys"})
        assert s_code.status_code == 200
        s_sym = client.post("/api/v1/search/symbol", headers=headers, json={"repository_id": repo_id, "symbol_name": "app"})
        assert s_sym.status_code == 200
        print(f"    [+] Search API: Code and Symbol search executed successfully")

        # 6. Git
        g_status = client.get("/api/v1/git/status", headers=headers)
        assert g_status.status_code == 200
        g_log = client.get("/api/v1/git/log", headers=headers)
        assert g_log.status_code == 200
        print(f"    [+] Git API: Status and Log retrieved")

        # 7. Agent Run
        a_run = client.post("/api/v1/agent/runs", headers=headers, json={"project_id": proj_id, "repository_id": repo_id, "mode": "PLAN", "instruction": "Analyze architecture"})
        assert a_run.status_code in (201, 202)
        run_id = a_run.json()["data"]["run_id"]
        a_status = client.get(f"/api/v1/agent/runs/{run_id}", headers=headers)
        assert a_status.status_code == 200
        print(f"    [+] Agent API: Run {run_id} created and inspected")

        # Cleanup Project
        client.delete(f"/api/v1/projects/{proj_id}", headers=headers)
        print(f"    [+] Projects API: Cleaned up {proj_id}")

    return {"status": "PASS", "tested_modules": ["Projects", "Repositories", "Conversations", "Models", "Search", "Git", "Agent"]}


def test_auth_security_negative_battery() -> dict[str, Any]:
    print("\n[3/3] VERIFYING AUTH & SECURITY NEGATIVE TEST BATTERY...")
    base_url = "http://localhost:8000"

    with httpx.Client(base_url=base_url, timeout=5.0) as client:
        # Negative 1: Missing token -> 401
        res1 = client.get("/api/v1/projects")
        assert res1.status_code == 401, f"Expected 401 for missing token, got {res1.status_code}"
        print("    [+] Negative Test 1 (Missing Token): Rejected with 401 Unauthorized")

        # Negative 2: Tampered / Fake JWT token -> 401
        res2 = client.get("/api/v1/projects", headers={"Authorization": "Bearer fake.jwt.token_signature"})
        assert res2.status_code == 401, f"Expected 401 for invalid JWT, got {res2.status_code}"
        print("    [+] Negative Test 2 (Tampered JWT): Rejected with 401 Unauthorized")

        # Negative 3: Internal endpoint with tampered HMAC -> 401/403
        with httpx.Client(base_url="http://localhost:8001", timeout=5.0) as internal_client:
            res3 = internal_client.get("/v1/agent/runs/fake_run", headers={"X-Internal-Service-Token": "forge-gateway:9999999999:bad_signature"})
            assert res3.status_code in (401, 403), f"Expected 401 or 403 for tampered HMAC, got {res3.status_code}"
            print(f"    [+] Negative Test 3 (Tampered Internal HMAC): Rejected with {res3.status_code} Auth Denial")

    return {"status": "PASS", "negative_cases_verified": 3}


def run_phase_3_api_certification(run_label: str = "RUN_A") -> dict[str, Any]:
    print(f"\n========================================================")
    print(f"[*] EXECUTING PHASE 3 API + SWAGGER 8/8 CERTIFICATION: {run_label}")
    print(f"========================================================")

    swagger_res = test_swagger_endpoints()
    gateway_res = test_gateway_api_matrix()
    security_res = test_auth_security_negative_battery()

    return {
        "status": "PASS",
        "swagger_services": len(swagger_res),
        "gateway_matrix": gateway_res["status"],
        "security_battery": security_res["status"],
    }


if __name__ == "__main__":
    res_a = run_phase_3_api_certification("RUN_A")
    res_b = run_phase_3_api_certification("RUN_B")

    print("\n========================================================")
    print("PHASE 3 DOUBLE EXECUTION VERIFICATION SUMMARY:")
    print(f"Run A Result: {res_a['status']} | 8/8 Microservices Swagger PASS")
    print(f"Run B Result: {res_b['status']} | 8/8 Microservices Swagger PASS")
    assert res_a["status"] == "PASS" and res_b["status"] == "PASS"
    print("========================================================")
    print("PHASE 3 API CERTIFICATION: >>> 100% PASS (8/8 SWAGGER + SECURITY) <<<")
    print("========================================================")
