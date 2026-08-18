from pathlib import Path
import uuid

import pytest
from fastapi.testclient import TestClient

from services.git.app.main import app as git_app
from services.git.app.services.git_service import GitService
from services.repository.app.main import app as repo_app
from services.tools.app.main import app as tools_app
from services.tools.app.patching.patch_engine import PatchEngine
from services.tools.app.sandbox.security_sandbox import SecuritySandbox
from shared.exceptions.handlers import UnauthorizedException, ValidationException

tools_client = TestClient(tools_app)
git_client = TestClient(git_app)
repo_client = TestClient(repo_app)


def get_internal_headers() -> dict[str, str]:
    from services.gateway.app.core.internal_auth import InternalAuthManager

    token = InternalAuthManager().generate_internal_token("test-client")
    return {"X-Internal-Service-Token": token}


def test_security_sandbox() -> None:
    """Verify traversal blocking, dangerous-command rejection, and secret masking."""
    sandbox = SecuritySandbox(workspace_root="./workspace")
    safe_path = sandbox.validate_safe_path("sub/file.txt")
    assert "workspace" in str(safe_path)

    with pytest.raises(UnauthorizedException):
        sandbox.validate_safe_path("../../etc/passwd")

    with pytest.raises(UnauthorizedException):
        sandbox.validate_safe_command("rm -rf /")

    masked = SecuritySandbox.mask_secrets(
        'Log token: secret_key="my_super_secret_token_123"'
    )
    assert "my_super_secret_token_123" not in masked
    assert "***MASKED***" in masked


def test_patch_engine_rollback() -> None:
    """Verify PatchEngine rollback when a multi-file patch fails."""
    sandbox = SecuritySandbox(workspace_root="./workspace")
    engine = PatchEngine(sandbox)
    repository_root = sandbox.workspace_root

    file_a = sandbox.validate_safe_path(
        "test_a.txt",
        base_root=repository_root,
    )
    file_a.write_text("original content a", encoding="utf-8")

    try:
        with pytest.raises(ValidationException):
            engine.apply_file_patches(
                repository_root=repository_root,
                files_to_modify=[
                    {
                        "path": "test_a.txt",
                        "patch": "modified content a",
                    },
                    {
                        "path": "../../../forbidden.txt",
                        "patch": "bad patch",
                    },
                ],
            )

        assert file_a.read_text(encoding="utf-8") == "original content a"
    finally:
        if file_a.exists():
            file_a.unlink()


@pytest.mark.asyncio
async def test_tools_api_endpoints() -> None:
    """Verify repository-scoped Tool Execution Service REST APIs."""
    headers = get_internal_headers()
    repo_root = Path(".").resolve()
    smoke_name = f"_forgeai_tool_smoke_{uuid.uuid4().hex[:10]}.py"
    smoke_path = repo_root / smoke_name

    repo_resp = repo_client.post(
        "/v1/repositories/register",
        headers=headers,
        json={
            "name": f"ForgeAI Tools Test Repo {uuid.uuid4().hex[:8]}",
            "path": str(repo_root).replace("\\", "/"),
        },
    )
    assert repo_resp.status_code == 201

    repository_id = repo_resp.json()["data"]["id"]

    smoke_path.write_text(
        "def test_forgeai_tool_smoke():\n"
        "    assert 1 + 1 == 2\n",
        encoding="utf-8",
    )

    try:
        write_resp = tools_client.post(
            "/internal/v1/tools/write-file",
            headers=headers,
            json={
                "repository_id": repository_id,
                "path": "sample.py",
                "content": "print('hello world')\n",
            },
        )
        assert write_resp.status_code == 200

        read_resp = tools_client.post(
            "/internal/v1/tools/read-file",
            headers=headers,
            json={
                "repository_id": repository_id,
                "path": "sample.py",
            },
        )
        assert read_resp.status_code == 200
        assert "print('hello world')" in read_resp.json()["data"]["content"]

        search_resp = tools_client.post(
            "/internal/v1/tools/search",
            headers=headers,
            json={
                "repository_id": repository_id,
                "pattern": "hello",
            },
        )
        assert search_resp.status_code == 200

        assert any(
            item.get("path") == "sample.py"
            for item in search_resp.json()["data"]
        )

        patch_resp = tools_client.post(
            "/internal/v1/tools/apply-patch",
            headers=headers,
            json={
                "repository_id": repository_id,
                "files_to_create": [
                    {
                        "path": "new_mod.py",
                        "content": "# New module",
                    }
                ],
                "files_to_modify": [
                    {
                        "path": "sample.py",
                        "content": "print('updated')",
                    }
                ],
            },
        )
        assert patch_resp.status_code == 200

        verify_resp = tools_client.post(
            "/internal/v1/tools/read-file",
            headers=headers,
            json={
                "repository_id": repository_id,
                "path": "sample.py",
            },
        )
        assert verify_resp.status_code == 200
        assert "print('updated')" in verify_resp.json()["data"]["content"]

        created_resp = tools_client.post(
            "/internal/v1/tools/read-file",
            headers=headers,
            json={
                "repository_id": repository_id,
                "path": "new_mod.py",
            },
        )
        assert created_resp.status_code == 200
        assert "# New module" in created_resp.json()["data"]["content"]

        command_resp = tools_client.post(
            "/internal/v1/tools/run-command",
            headers=headers,
            json={
                "repository_id": repository_id,
                "command": "python --version",
            },
        )
        assert command_resp.status_code == 200
        command_data = command_resp.json()["data"]
        assert command_data["exit_code"] == 0
        assert Path(command_data["cwd"]).resolve() == repo_root

        test_resp = tools_client.post(
            "/internal/v1/tools/run-test",
            headers=headers,
            json={
                "repository_id": repository_id,
                "test_path": smoke_name,
            },
        )
        assert test_resp.status_code == 200
        test_data = test_resp.json()["data"]
        assert test_data["passed"] is True
        assert test_data["exit_code"] == 0
        assert Path(test_data["cwd"]).resolve() == repo_root

        lint_resp = tools_client.post(
            "/internal/v1/tools/run-linter",
            headers=headers,
            json={
                "repository_id": repository_id,
                "target_path": smoke_name,
            },
        )
        assert lint_resp.status_code == 200
        assert lint_resp.json()["data"]["exit_code"] == 0

        formatter_resp = tools_client.post(
            "/internal/v1/tools/run-formatter",
            headers=headers,
            json={
                "repository_id": repository_id,
                "target_path": smoke_name,
            },
        )
        assert formatter_resp.status_code == 200
        assert formatter_resp.json()["data"]["exit_code"] == 0

        delete_resp = tools_client.post(
            "/internal/v1/tools/delete-file",
            headers=headers,
            json={
                "repository_id": repository_id,
                "path": "sample.py",
            },
        )
        assert delete_resp.status_code == 200
    finally:
        for relative_path in ("sample.py", "new_mod.py", smoke_name):
            target = repo_root / relative_path
            if target.exists():
                target.unlink()


def test_apply_patch_requires_repository_id() -> None:
    headers = get_internal_headers()

    resp = tools_client.post(
        "/internal/v1/tools/apply-patch",
        headers=headers,
        json={
            "files_to_create": [
                {
                    "path": "should_not_exist.py",
                    "content": "blocked",
                }
            ]
        },
    )

    assert resp.status_code == 422


def test_git_service_and_apis() -> None:
    """Verify Git Service and REST API endpoints."""
    headers = get_internal_headers()
    service = GitService()
    status_data = service.get_status()
    assert "branch" in status_data

    st_resp = git_client.get("/v1/git/status", headers=headers)
    assert st_resp.status_code == 200

    diff_resp = git_client.get("/v1/git/diff", headers=headers)
    assert diff_resp.status_code == 200

    log_resp = git_client.get("/v1/git/log?limit=5", headers=headers)
    assert log_resp.status_code == 200

    original_branch = status_data["branch"]
    branch_name = f"feature/forgeai-test-{uuid.uuid4().hex[:10]}"

    branch_resp = git_client.post(
        "/v1/git/branches",
        headers=headers,
        json={"branch_name": branch_name, "checkout": True},
    )
    assert branch_resp.status_code == 201

    try:
        checkout_resp = git_client.post(
            "/v1/git/checkout",
            headers=headers,
            json={"target": branch_name},
        )
        assert checkout_resp.status_code == 200

        commit_resp = git_client.post(
            "/v1/git/commit",
            headers=headers,
            json={"message": f"test: {branch_name}"},
        )
        assert commit_resp.status_code == 201
    finally:
        current_branch = service.get_status().get("branch")
        if current_branch == branch_name:
            git_client.post(
                "/v1/git/checkout",
                headers=headers,
                json={"target": original_branch},
            )

        git_client.delete(
            f"/v1/git/branches/{branch_name}",
            headers=headers,
        )