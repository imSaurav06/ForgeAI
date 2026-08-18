import time
from pathlib import Path
from typing import Any

from services.tools.app.runners.terminal_runner import TerminalRunner


class TestAndQualityRunners:
    """Pytest, build, lint and formatter runners with explicit repository cwd."""

    def __init__(self, terminal_runner: TerminalRunner | None = None) -> None:
        self.terminal = terminal_runner or TerminalRunner()

    async def run_pytest(
        self,
        test_path: str | None = None,
        timeout_sec: float = 60.0,
        cwd: str | Path | None = None,
        base_root: str | Path | None = None,
    ) -> dict[str, Any]:
        """Execute pytest inside the selected repository boundary."""
        actual_test_path = test_path
        if actual_test_path and cwd:
            target_p = Path(cwd) / actual_test_path
            if not target_p.exists():
                matched = [p for p in Path(cwd).glob(f"**/{actual_test_path}") if not any(part.startswith(".") for part in p.parts)]
                if not matched:
                    matched = list(Path(cwd).glob(f"**/{actual_test_path}"))
                if matched:
                    actual_test_path = str(matched[0].relative_to(cwd)).replace("\\", "/")

        cmd = (
            f"python -m pytest {actual_test_path} -o pythonpath=."
            if actual_test_path
            else "python -m pytest -o pythonpath=."
        )

        start = time.perf_counter()
        res = await self.terminal.run_command(
            command=cmd,
            cwd=cwd,
            timeout_sec=timeout_sec,
            base_root=base_root,
        )

        return {
            "runner": "pytest",
            "passed": res["exit_code"] == 0,
            "exit_code": res["exit_code"],
            "output": res["output"],
            "stdout": res.get("stdout", ""),
            "stderr": res.get("stderr", ""),
            "duration_seconds": round(time.perf_counter() - start, 2),
            "test_path": test_path or "all",
            "cwd": res.get("cwd"),
        }

    async def run_linter(
        self,
        target_path: str | None = None,
        cwd: str | Path | None = None,
        base_root: str | Path | None = None,
    ) -> dict[str, Any]:
        """Execute ruff linter inside the selected repository boundary."""
        cmd = (
            f"python -m ruff check {target_path}"
            if target_path
            else "python -m ruff check ."
        )

        res = await self.terminal.run_command(
            command=cmd,
            cwd=cwd,
            base_root=base_root,
        )

        return {
            "runner": "ruff_linter",
            "passed": res["exit_code"] == 0,
            "exit_code": res["exit_code"],
            "output": res["output"],
            "cwd": res.get("cwd"),
        }

    async def run_formatter(
        self,
        target_path: str | None = None,
        cwd: str | Path | None = None,
        base_root: str | Path | None = None,
    ) -> dict[str, Any]:
        """Execute ruff formatter inside the selected repository boundary."""
        cmd = (
            f"python -m ruff format {target_path}"
            if target_path
            else "python -m ruff format ."
        )

        res = await self.terminal.run_command(
            command=cmd,
            cwd=cwd,
            base_root=base_root,
        )

        return {
            "runner": "ruff_formatter",
            "passed": res["exit_code"] == 0,
            "exit_code": res["exit_code"],
            "output": res["output"],
            "cwd": res.get("cwd"),
        }

    async def run_build(
        self,
        command: str | None = None,
        cwd: str | Path | None = None,
        base_root: str | Path | None = None,
    ) -> dict[str, Any]:
        """Execute the build command inside the selected repository boundary."""
        res = await self.terminal.run_command(
            command=command or "python -m build",
            cwd=cwd,
            base_root=base_root,
        )

        return {
            "runner": "build_runner",
            "passed": res["exit_code"] == 0,
            "exit_code": res["exit_code"],
            "output": res["output"],
            "cwd": res.get("cwd"),
        }

    async def run_typecheck(
        self,
        target_path: str | None = None,
        cwd: str | Path | None = None,
        base_root: str | Path | None = None,
    ) -> dict[str, Any]:
        """Execute typecheck verification (mypy or compile check) inside repository."""
        cmd = f"python -m py_compile {target_path}" if target_path else "python -c 'import py_compile, glob; [py_compile.compile(f, doraise=True) for f in glob.glob(\"**/*.py\", recursive=True) if not any(p.startswith(\".\") for p in f.split(\"/\"))]'"
        res = await self.terminal.run_command(
            command=cmd,
            cwd=cwd,
            base_root=base_root,
        )
        return {
            "runner": "typecheck_runner",
            "passed": res["exit_code"] == 0,
            "exit_code": res["exit_code"],
            "output": res["output"],
            "cwd": res.get("cwd"),
        }