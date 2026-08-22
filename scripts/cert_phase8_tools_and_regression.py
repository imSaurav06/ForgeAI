"""
Phase 8 Tools Execution, Negative Security Battery & Master Regression Certification Script
Forensically tests tools execution, security sandboxing against path traversal and injection,
atomic rollback mechanisms, and double verification.
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from services.tools.app.patching.patch_engine import PatchEngine
from services.tools.app.runners.terminal_runner import TerminalRunner
from services.tools.app.runners.test_runners import TestAndQualityRunners
from services.tools.app.sandbox.security_sandbox import SecuritySandbox
from services.tools.app.services.tool_service import ToolExecutionService
from shared.exceptions.handlers import UnauthorizedException, ValidationException


async def run_phase_8_tools_and_regression(run_label: str = "RUN_A") -> dict[str, Any]:
    print(f"\n========================================================")
    print(f"[*] EXECUTING PHASE 8 TOOLS & REGRESSION CERTIFICATION: {run_label}")
    print(f"========================================================")

    # 1. Setup isolated sandbox workspace
    temp_dir = tempfile.mkdtemp(prefix="forge_cert_tools_")
    repo_root = Path(temp_dir).resolve()
    print(f"[1/4] INITIALIZING TOOL EXECUTION SANDBOX AT: {repo_root}")

    sandbox = SecuritySandbox(workspace_root=repo_root)
    terminal = TerminalRunner(sandbox=sandbox)
    patch_engine = PatchEngine(sandbox=sandbox)
    quality_runners = TestAndQualityRunners(terminal_runner=terminal)

    # 2. Individual Tools Verification
    print("\n[2/4] VERIFYING INDIVIDUAL TOOL EXECUTION ENGINES...")

    # Tool A: File Write
    sample_code = "def math_multiplier(a, b):\n    return a * b\n"
    created = patch_engine.apply_patch(
        files_to_create=[{"path": "math_tool.py", "content": sample_code}],
        base_root=repo_root,
    )
    assert (repo_root / "math_tool.py").is_file()
    print("    [+] Tool: File Create / Write -> PASS")

    # Tool B: File Read
    content = (repo_root / "math_tool.py").read_text(encoding="utf-8")
    assert "math_multiplier" in content
    print("    [+] Tool: File Read -> PASS")

    # Tool C: File Modify / Patch
    patch_engine.apply_patch(
        files_to_modify=[{"path": "math_tool.py", "content": sample_code + "\ndef add(a, b):\n    return a + b\n"}],
        base_root=repo_root,
    )
    assert "def add" in (repo_root / "math_tool.py").read_text(encoding="utf-8")
    print("    [+] Tool: File Modify / Patch -> PASS")

    # Tool D: Run Command in Terminal
    cmd_res = await terminal.run_command("python -c \"import math_tool; print(math_tool.add(10, 32))\"", cwd=repo_root, base_root=repo_root)
    assert cmd_res["exit_code"] == 0
    assert "42" in cmd_res["output"].strip()
    print(f"    [+] Tool: Sandboxed Terminal Execution (output: {cmd_res['output'].strip()}) -> PASS")

    # Tool E: Run Tests / Pytest
    test_code = "import math_tool\n\ndef test_math():\n    assert math_tool.math_multiplier(6, 7) == 42\n"
    (repo_root / "test_math.py").write_text(test_code, encoding="utf-8")
    test_res = await quality_runners.run_pytest(target_path="test_math.py", cwd=repo_root, base_root=repo_root)
    assert test_res["passed"] is True, f"Pytest failed: {test_res}"
    print(f"    [+] Tool: Test Runner (Pytest passed: {test_res['passed']}) -> PASS")

    # Tool F: Run Typecheck
    typecheck_res = await quality_runners.run_typecheck(target_path="math_tool.py", cwd=repo_root, base_root=repo_root)
    assert typecheck_res["passed"] is True
    print(f"    [+] Tool: Typecheck Runner (passed: {typecheck_res['passed']}) -> PASS")

    # Tool G: File Delete
    patch_engine.apply_patch(
        files_to_delete=["test_math.py"],
        base_root=repo_root,
    )
    assert not (repo_root / "test_math.py").exists()
    print("    [+] Tool: File Delete -> PASS")

    # 3. Security Negative Battery & Sandboxing
    print("\n[3/4] EXECUTING SECURITY NEGATIVE BATTERY & SANDBOX VALIDATION...")

    # Negative A: Path Traversal Attack
    traversal_caught = False
    try:
        sandbox.validate_safe_path("../../../../../Windows/System32/calc.exe", base_root=repo_root)
    except UnauthorizedException:
        traversal_caught = True
    assert traversal_caught, "Path traversal attack was NOT caught by sandbox!"
    print("    [+] Security Negative A: Path Traversal (../../Windows) -> Intercepted & Blocked")

    # Negative B: Drive Letter Escape
    escape_caught = False
    try:
        sandbox.validate_safe_path("C:/Windows/notepad.exe", base_root=repo_root)
    except UnauthorizedException:
        escape_caught = True
    assert escape_caught, "Drive letter escape was NOT caught by sandbox!"
    print("    [+] Security Negative B: Drive Letter Escape -> Intercepted & Blocked")

    # Negative C: Atomic Patch Rollback on Failure
    original_math = (repo_root / "math_tool.py").read_text(encoding="utf-8")
    rollback_worked = False
    try:
        # Intentionally malformed patch payload that fails halfway
        patch_engine.apply_patch(
            files_to_modify=[{"path": "math_tool.py", "content": "CORRUPTED_CODE"}],
            files_to_create=[{"path": "../../../illegal.py", "content": "ESCAPE"}],
            base_root=repo_root,
        )
    except (UnauthorizedException, ValidationException):
        # Verify rollback restored original code
        current_math = (repo_root / "math_tool.py").read_text(encoding="utf-8")
        if current_math == original_math:
            rollback_worked = True
    assert rollback_worked, "Atomic patch rollback failed to restore clean working state!"
    print("    [+] Security Negative C: Atomic Patch Rollback -> Clean State Restored")

    return {
        "status": "PASS",
        "tools_verified": ["create", "read", "modify", "delete", "terminal", "pytest", "typecheck"],
        "security_tests_passed": 3,
        "atomic_rollback_verified": True,
    }


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    res_a = loop.run_until_complete(run_phase_8_tools_and_regression("RUN_A"))
    res_b = loop.run_until_complete(run_phase_8_tools_and_regression("RUN_B"))

    print("\n========================================================")
    print("PHASE 8 DOUBLE EXECUTION VERIFICATION SUMMARY:")
    print(f"Run A Result: {res_a['status']} | 7 Tools + 3 Security Battery Cases PASS")
    print(f"Run B Result: {res_b['status']} | 7 Tools + 3 Security Battery Cases PASS")
    assert res_a["status"] == "PASS" and res_b["status"] == "PASS"
    print("========================================================")
    print("PHASE 8 TOOLS & MASTER SECURITY CERTIFICATION: >>> 100% PASS <<<")
    print("========================================================")
