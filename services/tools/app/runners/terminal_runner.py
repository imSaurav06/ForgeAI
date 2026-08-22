import asyncio
import os
from pathlib import Path
from typing import Any

from services.tools.app.sandbox.security_sandbox import SecuritySandbox
from shared.logging.logger import logger


class TerminalRunner:
    """One-shot subprocess runner with explicit execution-root support."""

    def __init__(self, sandbox: SecuritySandbox | None = None) -> None:
        self.sandbox = sandbox or SecuritySandbox()

    async def run_command(
        self,
        command: str,
        cwd: str | Path | None = None,
        timeout_sec: float = 30.0,
        base_root: str | Path | None = None,
    ) -> dict[str, Any]:
        clean_cmd = self.sandbox.validate_safe_command(command)

        if base_root is not None:
            root = self.sandbox._resolve_base_root(base_root)
            work_dir = self.sandbox.validate_execution_path(cwd or root, root)
        else:
            work_dir = self.sandbox.validate_safe_path(cwd) if cwd else self.sandbox.workspace_root

        logger.info(
            "Executing terminal command '%s' in %s",
            SecuritySandbox.mask_secrets(clean_cmd),
            work_dir,
        )

        process: asyncio.subprocess.Process | None = None
        try:
            if os.name == "nt":
                shell_cmd = ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", clean_cmd]
                process = await asyncio.create_subprocess_exec(
                    *shell_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(work_dir),
                    env=os.environ.copy(),
                )
            else:
                process = await asyncio.create_subprocess_shell(
                    clean_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(work_dir),
                    env=os.environ.copy(),
                )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(), timeout=timeout_sec
            )
            stdout = SecuritySandbox.mask_secrets(stdout_bytes.decode("utf-8", errors="ignore"))
            stderr = SecuritySandbox.mask_secrets(stderr_bytes.decode("utf-8", errors="ignore"))
            return {
                "command": clean_cmd,
                "exit_code": process.returncode,
                "output": stdout + (f"\n{stderr}" if stderr else ""),
                "stdout": stdout,
                "stderr": stderr,
                "timeout": False,
                "cwd": str(work_dir),
            }
        except TimeoutError:
            if process is not None:
                try:
                    process.kill()
                except Exception:
                    pass
            message = f"Command timed out after {timeout_sec} seconds"
            return {"command": clean_cmd, "exit_code": -1, "output": message, "stdout": "", "stderr": message, "timeout": True, "cwd": str(work_dir)}
        except Exception as err:
            logger.error("Error executing command '%s': %s", clean_cmd, err)
            return {"command": clean_cmd, "exit_code": -1, "output": str(err), "stdout": "", "stderr": str(err), "timeout": False, "cwd": str(work_dir)}
