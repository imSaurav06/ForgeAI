import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from services.agent.app.core.workflows.orchestrator import AgentWorkflowOrchestrator
import httpx


@pytest.fixture
def orchestrator():
    return AgentWorkflowOrchestrator()


# ============================================================
# P0-1: AGENT PATCH APPLICATION CONTROL FLOW TESTS
# ============================================================

@pytest.mark.asyncio
async def test_apply_patch_valid_fenced_json(orchestrator):
    """Verify valid fenced JSON patch delegates to Tools Service and succeeds."""
    fenced_patch = """Here is the suggested fix:
```json
{
  "files_to_create": [{"path": "hello.py", "content": "print('hello')"}],
  "files_to_modify": [],
  "files_to_delete": []
}
```
Hope this helps!"""

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"success": True, "data": {"success": True, "created_count": 1}}
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        res = await orchestrator._apply_patch(fenced_patch, "repo_123")
        assert res == "Applied patch successfully"
        mock_post.assert_called_once()
        call_json = mock_post.call_args[1]["json"]
        assert call_json["repository_id"] == "repo_123"
        assert len(call_json["files_to_create"]) == 1
        assert call_json["files_to_create"][0]["path"] == "hello.py"


@pytest.mark.asyncio
async def test_apply_patch_valid_raw_json(orchestrator):
    """Verify raw JSON patch without code fences is parsed and applied."""
    raw_patch = '{"files_to_create": [], "files_to_modify": [{"path": "app.py", "content": "x = 2"}], "files_to_delete": []}'

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"success": True, "data": {"success": True, "modified_count": 1}}
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        res = await orchestrator._apply_patch(raw_patch, "repo_123")
        assert res == "Applied patch successfully"


@pytest.mark.asyncio
async def test_apply_patch_malformed_json_fails(orchestrator):
    """Verify malformed JSON raises RuntimeError and never passes."""
    bad_patch = "```json\n{ files_to_create: [ broken json \n```"
    with pytest.raises(RuntimeError) as exc_info:
        await orchestrator._apply_patch(bad_patch, "repo_123")
    assert "invalid patch payload" in str(exc_info.value).lower() or "json" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_apply_patch_empty_patch_fails(orchestrator):
    """Verify empty patch with no operations raises RuntimeError."""
    empty_patch = '{"files_to_create": [], "files_to_modify": [], "files_to_delete": []}'
    with pytest.raises(RuntimeError) as exc_info:
        await orchestrator._apply_patch(empty_patch, "repo_123")
    assert "empty patch" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_apply_patch_invalid_schema_fails(orchestrator):
    """Verify non-list operations or missing keys raise RuntimeError."""
    invalid_schema = '{"files_to_create": "not a list"}'
    with pytest.raises(RuntimeError) as exc_info:
        await orchestrator._apply_patch(invalid_schema, "repo_123")
    assert "files_to_create must be a list" in str(exc_info.value)


@pytest.mark.asyncio
async def test_apply_patch_missing_repository_fails(orchestrator):
    """Verify missing repository_id raises RuntimeError."""
    patch_data = '{"files_to_create": [{"path": "a.txt", "content": "1"}]}'
    with pytest.raises(RuntimeError) as exc_info:
        await orchestrator._apply_patch(patch_data, "")
    assert "repository_id is required" in str(exc_info.value)


@pytest.mark.asyncio
async def test_apply_patch_tools_service_failure_propagates(orchestrator):
    """Verify Tools Service HTTP 500 / error response propagates as failure."""
    patch_data = '{"files_to_create": [{"path": "a.txt", "content": "1"}]}'
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.HTTPStatusError("500 Internal Error", request=MagicMock(), response=MagicMock(status_code=500, text="Disk Error"))
        with pytest.raises(RuntimeError) as exc_info:
            await orchestrator._apply_patch(patch_data, "repo_123")
        assert "Failed to apply patch" in str(exc_info.value)


# ============================================================
# P0-2: TEST EXECUTION FAIL-CLOSED CONTRACT TESTS
# ============================================================

@pytest.mark.asyncio
async def test_execute_pytest_real_pass(orchestrator):
    """Verify real passing test with exit code 0 returns passed=True."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "success": True,
        "data": {
            "exit_code": 0,
            "passed": True,
            "output": "1 passed in 0.1s",
            "cwd": "F:/3_Netflix_Clone",
        }
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        res = await orchestrator._execute_pytest(repository_id="repo_123")
        assert res["passed"] is True
        assert res["exit_code"] == 0
        assert res["error"] is None


@pytest.mark.asyncio
async def test_execute_pytest_real_failure(orchestrator):
    """Verify test failure with exit code 1 returns passed=False."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "success": True,
        "data": {
            "exit_code": 1,
            "passed": False,
            "output": "1 failed in 0.1s",
            "cwd": "F:/3_Netflix_Clone",
        }
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        res = await orchestrator._execute_pytest(repository_id="repo_123")
        assert res["passed"] is False
        assert res["exit_code"] == 1
        assert "1 failed" in res["error"]


@pytest.mark.asyncio
async def test_execute_pytest_no_tests_collected_fails_closed(orchestrator):
    """Verify exit code 5 (no tests collected) is NOT treated as passed."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "success": True,
        "data": {
            "exit_code": 5,
            "passed": False,
            "output": "collected 0 items",
            "cwd": "F:/3_Netflix_Clone",
        }
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        res = await orchestrator._execute_pytest(repository_id="repo_123")
        assert res["passed"] is False
        assert res["exit_code"] == 5


@pytest.mark.asyncio
async def test_execute_pytest_tools_service_error_fails_closed(orchestrator):
    """Verify non-200 Tools Service response returns passed=False."""
    mock_resp = MagicMock()
    mock_resp.status_code = 503
    mock_resp.text = "Service Unavailable"

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        res = await orchestrator._execute_pytest(repository_id="repo_123")
        assert res["passed"] is False
        assert "HTTP 503" in res["error"]


@pytest.mark.asyncio
async def test_execute_pytest_exception_fails_closed(orchestrator):
    """Verify network/runtime exception returns passed=False."""
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.ConnectError("Connection refused")
        res = await orchestrator._execute_pytest(repository_id="repo_123")
        assert res["passed"] is False
        assert "exception" in res["error"].lower()


# ============================================================
# P0-3: REPOSITORY CONTEXT IN TEST EXECUTION
# ============================================================

@pytest.mark.asyncio
async def test_execute_pytest_missing_repository_id_fails_closed(orchestrator):
    """Verify missing repository_id is rejected without executing tools."""
    res = await orchestrator._execute_pytest(repository_id="")
    assert res["passed"] is False
    assert "repository_id is required" in res["error"]


@pytest.mark.asyncio
async def test_execute_pytest_repository_id_propagated(orchestrator):
    """Verify repository_id and test_path are propagated to Tools Service."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "success": True,
        "data": {
            "exit_code": 0,
            "passed": True,
            "output": "PASSED",
            "cwd": "F:/3_Netflix_Clone",
        }
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        await orchestrator._execute_pytest(pytest_path="tests/test_core.py", repository_id="repo_abc_999")
        mock_post.assert_called_once()
        call_json = mock_post.call_args[1]["json"]
        assert call_json["repository_id"] == "repo_abc_999"
        assert call_json["test_path"] == "tests/test_core.py"
