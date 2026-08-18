import json

import httpx

from services.gateway.app.api.dependencies.auth import generate_jwt_token
from services.gateway.app.core.internal_auth import InternalAuthManager

BASE_URL = "http://localhost:8000"
AGENT_URL = "http://localhost:8001"
LLM_URL = "http://localhost:8002"
REPO_URL = "http://localhost:8003"
RETRIEVAL_URL = "http://localhost:8004"
TOOLS_URL = "http://localhost:8005"
GIT_URL = "http://localhost:8006"
EVAL_URL = "http://localhost:8007"

jwt_token = generate_jwt_token("step8_admin_user", role="admin", secret_key="forge_ai_jwt_secret_key_2026_secure")
bearer_headers = {"Authorization": f"Bearer {jwt_token}"}
internal_token = InternalAuthManager().generate_internal_token()
internal_headers = {
    "X-Internal-Service-Token": internal_token,
    "X-User-ID": "step8_admin_user",
    "X-User-Role": "admin",
}

results = {}
evidence = {}

def run_step8_tests():
    print("=== STARTING STEP 8 FULL RUNTIME VERIFICATION ===")

    # 1. Gateway Health & Auth
    print("\n--- Step 2: Gateway Runtime Verification ---")
    r_health = httpx.get(f"{BASE_URL}/health")
    print(f"Gateway /health Status: {r_health.status_code}")
    evidence["gateway_health"] = r_health.json()

    r_unauth = httpx.get(f"{BASE_URL}/api/v1/models")
    print(f"Gateway /api/v1/models Unauthenticated Status: {r_unauth.status_code}")

    r_auth = httpx.get(f"{BASE_URL}/api/v1/models", headers=bearer_headers)
    print(f"Gateway /api/v1/models Authenticated Status: {r_auth.status_code}")
    print("Gateway /api/v1/models Body:", json.dumps(r_auth.json(), indent=2))
    evidence["gateway_models"] = r_auth.json()
    results["gateway"] = r_health.status_code == 200 and r_unauth.status_code == 401 and r_auth.status_code == 200

    # 2. Gateway -> Agent
    print("\n--- Step 3: Gateway -> Agent Verification ---")
    agent_payload = {
        "mode": "CODE",
        "instruction": "Create a python helper function for string validation",
        "project_id": "proj_step8_test",
        "repository_id": "repo_step8_test",
    }
    r_agent = httpx.post(f"{BASE_URL}/api/v1/agent/runs", json=agent_payload, headers=bearer_headers, timeout=60.0)
    print(f"Gateway -> Agent Run Status: {r_agent.status_code}")
    print("Agent Run Response:", json.dumps(r_agent.json(), indent=2))
    evidence["agent_run"] = r_agent.json()
    results["gateway_agent"] = r_agent.status_code in (200, 201, 202) and "data" in r_agent.json()

    # 3. Agent -> Repository (MongoDB)
    print("\n--- Step 4: Repository (MongoDB) Verification ---")
    repo_payload = {
        "name": "ForgeAI Step8 Repository",
        "path": "/app",
        "git_remote": "https://github.com/forgeai/step8.git",
        "branch": "main",
    }
    r_repo = httpx.post(f"{REPO_URL}/v1/repositories/register", json=repo_payload, headers=internal_headers, timeout=10.0)
    print(f"Repository Register Status: {r_repo.status_code}")
    print("Repository Response:", json.dumps(r_repo.json(), indent=2))
    evidence["repository_register"] = r_repo.json()
    results["repository_mongodb"] = r_repo.status_code in (200, 201)

    # 4. Agent -> Retrieval -> Qdrant
    print("\n--- Step 5: Retrieval -> Real Embeddings -> Qdrant Verification ---")
    retrieval_payload = {
        "repository_id": "repo_step8_test",
        "query": "def validate_jwt_token(token: str)",
        "limit": 3,
    }
    r_search = httpx.post(f"{RETRIEVAL_URL}/v1/search/semantic", json=retrieval_payload, headers=internal_headers, timeout=15.0)
    print(f"Retrieval Search Status: {r_search.status_code}")
    print("Retrieval Search Response:", json.dumps(r_search.json(), indent=2))
    evidence["retrieval_search"] = r_search.json()
    results["retrieval_qdrant"] = r_search.status_code == 200 and "data" in r_search.json()

    # 5. Agent -> LLM -> Ollama/Qwen
    print("\n--- Step 6: LLM -> Ollama -> Qwen Verification ---")
    llm_payload = {
        "prompt": "Write a Python function named check_even(n: int) -> bool that returns True if n is even.",
        "mode": "CODE",
        "model": "qwen2.5-coder:3b-instruct-q4_0",
    }
    r_llm = httpx.post(f"{LLM_URL}/v1/generate", json=llm_payload, headers=internal_headers, timeout=30.0)
    print(f"LLM Generation Status: {r_llm.status_code}")
    print("LLM Response Snippet:", json.dumps(r_llm.json(), indent=2)[:300])
    evidence["llm_generate"] = r_llm.json()

    # LLM Stream Verification
    print("Testing SSE Streaming from LLM Service...")
    tokens = []
    with httpx.stream("POST", f"{LLM_URL}/v1/stream", json={"prompt": "Say hello in one word", "mode": "ASK", "model": "qwen2.5-coder:3b-instruct-q4_0"}, headers=internal_headers, timeout=30.0) as r_stream:
        for line in r_stream.iter_lines():
            if line.startswith("data: "):
                tokens.append(line[6:])
    print(f"Streamed {len(tokens)} token chunks from Ollama! Snippet:", "".join(tokens)[:100])
    evidence["llm_stream_chunks_count"] = len(tokens)
    results["llm_ollama"] = r_llm.status_code == 200 and len(tokens) > 0

    # 6. Tools Verification
    print("\n--- Step 7: Tools Workspace Operations Verification ---")
    tool_payload = {
        "path": "step8_test_file.py",
        "content": "def test_step8():\n    return 'Step 8 Container Workspace Test Successful'\n",
    }
    r_tool = httpx.post(f"{TOOLS_URL}/internal/v1/tools/write-file", json=tool_payload, headers=internal_headers, timeout=10.0)
    print(f"Tool Write File Status: {r_tool.status_code}")
    print("Tool Response:", json.dumps(r_tool.json(), indent=2))
    evidence["tools_write_file"] = r_tool.json()
    results["tools"] = r_tool.status_code in (200, 201)

    # 7. Git Verification
    print("\n--- Step 8: Git Workspace Operations Verification ---")
    r_git = httpx.get(f"{GIT_URL}/v1/git/status", headers=internal_headers, timeout=10.0)
    print(f"Git Status Status: {r_git.status_code}")
    print("Git Response:", json.dumps(r_git.json(), indent=2))
    evidence["git_status"] = r_git.json()
    results["git"] = r_git.status_code == 200

    # 8. Evaluation Verification
    print("\n--- Step 9: Evaluation Service Verification ---")
    eval_payload = {
        "run_id": "run_step8_test_001",
        "repository_id": "repo_step8_test",
    }
    r_eval = httpx.post(f"{EVAL_URL}/v1/evaluations/run", json=eval_payload, headers=internal_headers, timeout=10.0)
    print(f"Evaluation Status: {r_eval.status_code}")
    print("Evaluation Response:", json.dumps(r_eval.json(), indent=2))
    evidence["evaluation_run"] = r_eval.json()
    results["evaluation"] = r_eval.status_code in (200, 201)

    # 9. Authentication Bypassing & Spoofing Direct Test
    print("\n--- Step 10: Authentication Verification ---")
    r_direct_unauth = httpx.get(f"{REPO_URL}/v1/repositories")
    print(f"Direct Unauthenticated Access to Internal Microservice Status: {r_direct_unauth.status_code}")
    r_direct_invalid = httpx.get(f"{REPO_URL}/v1/repositories", headers={"X-Internal-Service-Token": "invalid_fake_token"})
    print(f"Direct Invalid Token Access Status: {r_direct_invalid.status_code}")
    r_direct_auth = httpx.get(f"{REPO_URL}/v1/repositories/register", headers=internal_headers)
    print(f"Direct Authenticated Access (with token) Status: {r_direct_auth.status_code}")
    results["auth_enforcement"] = r_direct_unauth.status_code == 401 and r_direct_invalid.status_code == 401 and r_direct_auth.status_code in (404, 405, 422, 200, 201)

    print("\n=== VERIFICATION RESULTS SUMMARY ===")
    all_passed = True
    for k, v in results.items():
        print(f" - {k}: {'PASS' if v else 'FAIL'}")
        if not v:
            all_passed = False

    if all_passed:
        print("\nALL STEP 8 RUNTIME TESTS PASSED 100%!")

if __name__ == "__main__":
    run_step8_tests()
