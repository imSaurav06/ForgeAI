import asyncio
import os
import signal
import sys
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services.tools.app.main import app as tools_app
from services.tools.app.runners.pty_session_manager import PTYSessionManager
from services.tools.app.runners.pty_terminal import PTYTerminalSession
from services.tools.app.services.tool_service import ToolExecutionService
from services.repository.app.main import app as repo_app
from shared.exceptions.handlers import UnauthorizedException, ValidationException

tools_client = TestClient(tools_app)
repo_client = TestClient(repo_app)

TEST_WORKSPACE = r"F:\3_Netflix_Clone" if os.path.exists(r"F:\3_Netflix_Clone") else str(Path("./workspace").resolve())


def get_internal_headers() -> dict[str, str]:
    from services.gateway.app.core.internal_auth import InternalAuthManager
    token = InternalAuthManager().generate_internal_token("test-terminal-client")
    return {"X-Internal-Service-Token": token}


@pytest.mark.asyncio
async def test_regression_a_exit_code_isolation():
    """
    TEST A — exit code isolation
    cmd /c exit 7 -> exit_code = 7
    echo AFTER_EXIT_7 -> exit_code = 0
    """
    manager = PTYSessionManager()
    session_id = f"test-exit-code-{uuid.uuid4().hex[:8]}"

    session = await manager.get_or_create(
        session_id=session_id,
        workspace=TEST_WORKSPACE,
        shell="cmd.exe" if os.name == "nt" else "/bin/bash",
        base_root=TEST_WORKSPACE,
    )
    assert session.terminal.is_alive

    try:
        # 1. Exit code 7
        res1 = await manager.execute_command(
            session_id=session_id,
            command="cmd /c exit 7" if os.name == "nt" else "exit 7",
        )
        assert res1["status"] == "completed"
        assert res1["exit_code"] == 7

        # 2. Subsequent command must NOT inherit errorlevel 7
        res2 = await manager.execute_command(
            session_id=session_id,
            command="echo AFTER_EXIT_7",
        )
        assert res2["status"] == "completed"
        assert res2["exit_code"] == 0
        assert "AFTER_EXIT_7" in str(res2["output"])

    finally:
        await manager.remove(session_id)


@pytest.mark.asyncio
async def test_regression_b_interrupt_recovery():
    """
    TEST B — interrupt regression
    Start: ping 127.0.0.1 -t
    Send explicit interrupt.
    Then execute: echo AFTER_INTERRUPT
    Expected: status = completed, exit_code = 0, output contains AFTER_INTERRUPT
    """
    manager = PTYSessionManager()
    session_id = f"test-interrupt-{uuid.uuid4().hex[:8]}"

    session = await manager.get_or_create(
        session_id=session_id,
        workspace=TEST_WORKSPACE,
        shell="cmd.exe" if os.name == "nt" else "/bin/bash",
        base_root=TEST_WORKSPACE,
    )
    assert session.terminal.is_alive

    try:
        # Start a long-running process
        ping_cmd = "ping 127.0.0.1 -t" if os.name == "nt" else "ping 127.0.0.1"
        ping_task = asyncio.create_task(
            manager.execute_command(
                session_id=session_id,
                command=ping_cmd,
                timeout=10.0,
            )
        )

        # Allow process to start streaming
        await asyncio.sleep(1.5)

        # Interrupt the terminal
        await session.terminal.interrupt()

        ping_res = await ping_task
        assert ping_res["status"] in ("completed", "timeout")

        # Give shell a moment to settle
        await asyncio.sleep(0.5)

        # Post-interrupt command execution must succeed with exit code 0
        res_after = await manager.execute_command(
            session_id=session_id,
            command="echo AFTER_INTERRUPT",
        )
        assert res_after["status"] == "completed"
        assert res_after["exit_code"] == 0
        assert "AFTER_INTERRUPT" in str(res_after["output"])

    finally:
        await manager.remove(session_id)


@pytest.mark.asyncio
async def test_regression_c_cwd_persistence():
    r"""
    TEST C — cwd persistence
    cd src then cd -> Expected path F:\3_Netflix_Clone\src
    """
    manager = PTYSessionManager()
    session_id = f"test-cwd-{uuid.uuid4().hex[:8]}"

    session = await manager.get_or_create(
        session_id=session_id,
        workspace=TEST_WORKSPACE,
        shell="cmd.exe" if os.name == "nt" else "/bin/bash",
        base_root=TEST_WORKSPACE,
    )

    try:
        # Check if src directory exists in workspace
        src_exists = os.path.isdir(os.path.join(TEST_WORKSPACE, "src"))

        if src_exists:
            res_cd = await manager.execute_command(session_id, "cd src")
            assert res_cd["status"] == "completed"
            assert res_cd["exit_code"] == 0

            res_pwd = await manager.execute_command(session_id, "cd" if os.name == "nt" else "pwd")
            assert res_pwd["status"] == "completed"
            assert res_pwd["exit_code"] == 0
            assert "src" in str(res_pwd["output"])

            # cd back
            await manager.execute_command(session_id, "cd ..")
        else:
            res_pwd = await manager.execute_command(session_id, "cd" if os.name == "nt" else "pwd")
            assert res_pwd["status"] == "completed"
            assert res_pwd["exit_code"] == 0

    finally:
        await manager.remove(session_id)


@pytest.mark.asyncio
async def test_regression_d_crud_through_terminal():
    """
    TEST D — CRUD through terminal
    Create file, Read file, Update file, Read updated file, Delete file, Verify deletion.
    """
    manager = PTYSessionManager()
    session_id = f"test-crud-{uuid.uuid4().hex[:8]}"
    test_filename = f"_crud_test_{uuid.uuid4().hex[:6]}.txt"
    test_filepath = os.path.join(TEST_WORKSPACE, test_filename)

    session = await manager.get_or_create(
        session_id=session_id,
        workspace=TEST_WORKSPACE,
        shell="cmd.exe" if os.name == "nt" else "/bin/bash",
        base_root=TEST_WORKSPACE,
    )

    try:
        # 1. Create file
        r_create = await manager.execute_command(
            session_id,
            f"echo INITIAL_CONTENT > {test_filename}"
        )
        assert r_create["status"] == "completed"
        assert r_create["exit_code"] == 0
        assert os.path.exists(test_filepath)

        # 2. Read file
        r_read = await manager.execute_command(
            session_id,
            f"type {test_filename}" if os.name == "nt" else f"cat {test_filename}"
        )
        assert r_read["status"] == "completed"
        assert r_read["exit_code"] == 0
        assert "INITIAL_CONTENT" in str(r_read["output"])

        # 3. Update file
        r_update = await manager.execute_command(
            session_id,
            f"echo UPDATED_CONTENT > {test_filename}"
        )
        assert r_update["status"] == "completed"
        assert r_update["exit_code"] == 0

        # 4. Read updated file
        r_read2 = await manager.execute_command(
            session_id,
            f"type {test_filename}" if os.name == "nt" else f"cat {test_filename}"
        )
        assert r_read2["status"] == "completed"
        assert r_read2["exit_code"] == 0
        assert "UPDATED_CONTENT" in str(r_read2["output"])

        # 5. Delete file
        r_del = await manager.execute_command(
            session_id,
            f"del {test_filename}" if os.name == "nt" else f"rm {test_filename}"
        )
        assert r_del["status"] == "completed"
        assert r_del["exit_code"] == 0
        assert not os.path.exists(test_filepath)

    finally:
        if os.path.exists(test_filepath):
            os.remove(test_filepath)
        await manager.remove(session_id)


@pytest.mark.asyncio
async def test_regression_e_long_running_and_interrupt():
    """
    TEST E — long-running command
    Verify command stays alive, streams output, explicit interrupt works, session remains usable afterward.
    """
    manager = PTYSessionManager()
    session_id = f"test-longrun-{uuid.uuid4().hex[:8]}"

    session = await manager.get_or_create(
        session_id=session_id,
        workspace=TEST_WORKSPACE,
        shell="cmd.exe" if os.name == "nt" else "/bin/bash",
        base_root=TEST_WORKSPACE,
    )

    try:
        # Subscribe to live output
        sub_queue = await manager.subscribe(session_id, "test_listener", replay_scrollback=False)
        assert sub_queue is not None

        # Start long-running python script
        py_cmd = 'python -c "import time; [print(f\'TICK_{i}\', flush=True) or time.sleep(0.5) for i in range(20)]"'
        task = asyncio.create_task(manager.execute_command(session_id, py_cmd, timeout=10.0))

        # Check streaming output
        received = []
        for _ in range(3):
            chunk = await asyncio.wait_for(sub_queue.get(), timeout=3.0)
            received.append(chunk.decode("utf-8", errors="replace"))

        assert any("TICK" in c for c in received)

        # Explicit interrupt
        await session.terminal.interrupt()

        res = await task
        assert res["status"] in ("completed", "timeout")

        await manager.unsubscribe(session_id, "test_listener")

        # Session remains healthy and usable
        r_healthy = await manager.execute_command(session_id, "echo SESSION_HEALTHY")
        assert r_healthy["status"] == "completed"
        assert r_healthy["exit_code"] == 0
        assert "SESSION_HEALTHY" in str(r_healthy["output"])

    finally:
        await manager.remove(session_id)


@pytest.mark.asyncio
async def test_regression_f_node_npm_execution():
    """
    TEST F — Node/npm execution
    node --version and npm --version both must return exit_code 0.
    """
    manager = PTYSessionManager()
    session_id = f"test-node-npm-{uuid.uuid4().hex[:8]}"

    session = await manager.get_or_create(
        session_id=session_id,
        workspace=TEST_WORKSPACE,
        shell="cmd.exe" if os.name == "nt" else "/bin/bash",
        base_root=TEST_WORKSPACE,
    )

    try:
        # 1. node --version
        r_node = await manager.execute_command(session_id, "node --version")
        assert r_node["status"] == "completed"
        assert r_node["exit_code"] == 0
        assert "v" in str(r_node["output"])

        # 2. npm --version
        r_npm = await manager.execute_command(session_id, "npm --version")
        assert r_npm["status"] == "completed"
        assert r_npm["exit_code"] == 0
        assert any(ch.isdigit() for ch in str(r_npm["output"]))

    finally:
        await manager.remove(session_id)


@pytest.mark.asyncio
async def test_regression_g_real_build_execution():
    """
    TEST G — real build execution
    npm run build
    Must capture real output, return correct exit code, and not misreport previous exit code.
    """
    if not os.path.exists(r"F:\3_Netflix_Clone\package.json"):
        pytest.skip("F:\\3_Netflix_Clone test workspace not present")

    manager = PTYSessionManager()
    session_id = f"test-build-{uuid.uuid4().hex[:8]}"

    session = await manager.get_or_create(
        session_id=session_id,
        workspace=r"F:\3_Netflix_Clone",
        shell="cmd.exe" if os.name == "nt" else "/bin/bash",
        base_root=r"F:\3_Netflix_Clone",
    )

    try:
        # Run build
        r_build = await manager.execute_command(session_id, "npm run build", timeout=60.0)
        assert r_build["status"] == "completed"
        # The build in dummy project is expected to fail with exit code 1
        assert r_build["exit_code"] == 1
        assert "vite build" in str(r_build["output"])

        # Subsequent command must succeed and report 0
        r_after = await manager.execute_command(session_id, "echo BUILD_FINISHED_CLEANLY")
        assert r_after["status"] == "completed"
        assert r_after["exit_code"] == 0
        assert "BUILD_FINISHED_CLEANLY" in str(r_after["output"])

    finally:
        await manager.remove(session_id)


@pytest.mark.asyncio
async def test_rest_terminal_service_endpoints():
    """
    Verify full REST lifecycle through ToolExecutionService:
    /terminal/session, /terminal/execute, /terminal/interrupt.
    """
    headers = get_internal_headers()
    repo_root = Path(TEST_WORKSPACE).resolve()

    repo_resp = repo_client.post(
        "/v1/repositories/register",
        headers=headers,
        json={
            "name": f"Terminal REST Test Repo {uuid.uuid4().hex[:8]}",
            "path": str(repo_root).replace("\\", "/"),
        },
    )
    assert repo_resp.status_code == 201
    repository_id = repo_resp.json()["data"]["id"]
    session_id = f"rest-session-{uuid.uuid4().hex[:8]}"

    try:
        # Create session
        s_resp = tools_client.post(
            "/internal/v1/tools/terminal/session",
            headers=headers,
            json={
                "session_id": session_id,
                "repository_id": repository_id,
            },
        )
        assert s_resp.status_code == 200
        assert s_resp.json()["data"]["alive"] is True

        # Execute exit 7
        e1_resp = tools_client.post(
            "/internal/v1/tools/terminal/execute",
            headers=headers,
            json={
                "session_id": session_id,
                "command": "cmd /c exit 7" if os.name == "nt" else "exit 7",
            },
        )
        assert e1_resp.status_code == 200
        assert e1_resp.json()["data"]["exit_code"] == 7

        # Execute echo
        e2_resp = tools_client.post(
            "/internal/v1/tools/terminal/execute",
            headers=headers,
            json={
                "session_id": session_id,
                "command": "echo AFTER_EXIT_7",
            },
        )
        assert e2_resp.status_code == 200
        assert e2_resp.json()["data"]["exit_code"] == 0
        assert "AFTER_EXIT_7" in e2_resp.json()["data"]["output"]

        # Interrupt endpoint
        i_resp = tools_client.post(
            "/internal/v1/tools/terminal/interrupt",
            headers=headers,
            json={
                "session_id": session_id,
            },
        )
        assert i_resp.status_code == 200
        assert i_resp.json()["data"]["status"] == "interrupted"

    finally:
        svc = ToolExecutionService()
        await svc.agent_terminal_gateway.close(session_id)
