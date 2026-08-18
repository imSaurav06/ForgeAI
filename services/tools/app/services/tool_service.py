from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx

from services.tools.app.patching.patch_engine import PatchEngine
from services.tools.app.runners.terminal_runner import TerminalRunner
from services.tools.app.runners.test_runners import TestAndQualityRunners
from services.tools.app.sandbox.security_sandbox import SecuritySandbox
from services.tools.app.services.agent_terminal_gateway import AgentTerminalGateway
from shared.config.settings import get_settings
from shared.exceptions.handlers import NotFoundException


def _resolve_repo_path(repository_id: str | None) -> Path | None:
    """
    Resolve a repository ID to its canonical filesystem path.

    Resolution order:
    1. Local repository-service implementation/registry.
    2. Configured repository-service HTTP URL.

    No hardcoded Docker hostname is used, so local and containerized
    deployments can use the same configuration contract.
    """
    if not repository_id:
        return None

    try:
        from services.repository.app.services.repository_service import RepositoryService

        meta = RepositoryService().get_repository_metadata(repository_id)
        if meta and meta.path:
            return Path(meta.path).resolve()
    except Exception:
        pass

    try:
        settings = get_settings()
        base_url = settings.repository_service_url.rstrip("/")

        from services.gateway.app.core.internal_auth import InternalAuthManager

        internal_token = InternalAuthManager().generate_internal_token("tool-service")
        headers = {
            "X-Internal-Service-Token": internal_token,
        }

        # Repository Service exposes metadata/status through /{id}/status.
        # There is intentionally no GET /v1/repositories/{id} route.
        repo_url = f"{base_url}/v1/repositories/{repository_id}/status"
        resp = httpx.get(
            repo_url,
            headers=headers,
            timeout=2.0,
        )

        if resp.status_code == 200:
            path = resp.json().get("data", {}).get("path")
            if path:
                return Path(path).resolve()
    except Exception:
        pass

    return None


class ToolExecutionService:
    """
    Tool Execution Service providing repository-scoped filesystem operations,
    one-shot command execution, persistent PTY terminal access, and quality
    runners.

    Repository-scoped operations must resolve a repository_id first. They do
    not silently fall back to the global application workspace.
    """

    SEARCH_IGNORED_DIRS = frozenset(
        {
            ".git",
            ".hg",
            ".svn",
            "node_modules",
            ".next",
            ".turbo",
            ".cache",
            ".pytest_cache",
            "__pycache__",
            ".mypy_cache",
            ".ruff_cache",
            ".venv",
            "venv",
            "env",
            "dist",
            "build",
            "coverage",
            "htmlcov",
            ".tox",
            ".eggs",
            "site-packages",
        }
    )

    SEARCH_MAX_FILE_BYTES = 4 * 1024 * 1024

    def __init__(self) -> None:
        self.sandbox = SecuritySandbox()
        self.patch_engine = PatchEngine(self.sandbox)
        self.terminal_runner = TerminalRunner(self.sandbox)
        self.quality_runners = TestAndQualityRunners(self.terminal_runner)
        self.agent_terminal_gateway = AgentTerminalGateway()

    def _require_repo_path(self, repository_id: str | None) -> Path:
        if not repository_id:
            raise NotFoundException(
                message="repository_id is required for repository-scoped tool execution"
            )

        repo_path = _resolve_repo_path(repository_id)

        if repo_path is None:
            raise NotFoundException(
                message=f"Repository '{repository_id}' could not be resolved"
            )

        if not repo_path.is_dir():
            raise NotFoundException(
                message=f"Repository path does not exist: {repo_path}"
            )

        return repo_path

    def read_file(
        self,
        path: str,
        start_line: int | None = None,
        end_line: int | None = None,
        repository_id: str | None = None,
    ) -> dict[str, Any]:
        repo_path = self._require_repo_path(repository_id)
        safe_path = self.sandbox.validate_safe_path(path, base_root=repo_path)

        if not safe_path.is_file():
            raise NotFoundException(
                message=f"File '{path}' does not exist in repository"
            )

        content = safe_path.read_text(encoding="utf-8", errors="ignore")
        lines = content.splitlines()

        if start_line is not None or end_line is not None:
            start_index = (
                start_line - 1
                if start_line is not None and start_line > 0
                else 0
            )
            end_index = end_line if end_line is not None else len(lines)
            content = "\n".join(lines[start_index:end_index])

        return {
            "path": path,
            "content": content,
            "total_lines": len(lines),
        }

    def write_file(
        self,
        path: str,
        content: str,
        repository_id: str | None = None,
    ) -> dict[str, Any]:
        repo_path = self._require_repo_path(repository_id)
        safe_path = self.sandbox.validate_safe_path(path, base_root=repo_path)
        safe_path.parent.mkdir(parents=True, exist_ok=True)
        safe_path.write_text(content, encoding="utf-8")

        return {
            "path": path,
            "bytes_written": len(content.encode("utf-8")),
            "status": "written",
        }

    def delete_file(
        self,
        path: str,
        repository_id: str,
    ) -> dict[str, Any]:
        repo_path = self._require_repo_path(repository_id)
        safe_path = self.sandbox.validate_safe_path(path, base_root=repo_path)

        if safe_path.is_file():
            safe_path.unlink()
            return {"path": path, "status": "deleted"}

        raise NotFoundException(
            message=f"File '{path}' not found for deletion"
        )

    def search_files(
        self,
        pattern: str,
        repository_id: str,
        search_dir: str | None = None,
    ) -> list[dict[str, Any]]:
        repo_path = self._require_repo_path(repository_id)

        if not pattern:
            return []

        target_dir = (
            self.sandbox.validate_safe_path(
                search_dir,
                base_root=repo_path,
            )
            if search_dir
            else repo_path
        )

        if not target_dir.is_dir():
            return []

        needle = pattern.casefold()
        matches: list[dict[str, Any]] = []

        for root, dirs, files in os.walk(
            target_dir,
            topdown=True,
            followlinks=False,
        ):
            dirs[:] = [
                dirname
                for dirname in dirs
                if dirname not in self.SEARCH_IGNORED_DIRS
            ]

            root_path = Path(root)

            for filename in files:
                candidate = root_path / filename

                try:
                    if candidate.stat().st_size > self.SEARCH_MAX_FILE_BYTES:
                        continue

                    with candidate.open(
                        "r",
                        encoding="utf-8",
                        errors="ignore",
                    ) as handle:
                        text = handle.read()
                except (OSError, UnicodeError):
                    continue

                if needle not in text.casefold():
                    continue

                matches.append(
                    {
                        "path": str(candidate.relative_to(repo_path)).replace(
                            "\\",
                            "/",
                        ),
                        "matched": True,
                    }
                )

        return matches

    def apply_patch(
        self,
        repository_id: str,
        files_to_create: list[dict[str, str]] | None = None,
        files_to_modify: list[dict[str, str]] | None = None,
        files_to_delete: list[str] | None = None,
    ) -> dict[str, Any]:
        repo_path = self._require_repo_path(repository_id)

        return self.patch_engine.apply_file_patches(
            repository_root=repo_path,
            files_to_create=files_to_create,
            files_to_modify=files_to_modify,
            files_to_delete=files_to_delete,
        )

    async def run_command(
        self,
        command: str,
        cwd: str | None = None,
        timeout_sec: float = 30.0,
        repository_id: str | None = None,
    ) -> dict[str, Any]:
        repo_path = self._require_repo_path(repository_id)

        work_dir = (
            self.sandbox.validate_execution_path(
                cwd,
                base_root=repo_path,
            )
            if cwd
            else repo_path
        )

        return await self.terminal_runner.run_command(
            command=command,
            cwd=work_dir,
            timeout_sec=timeout_sec,
            base_root=repo_path,
        )

    async def create_terminal_session(
        self,
        session_id: str,
        workspace: str | None = None,
        shell: str | None = None,
        cols: int = 120,
        rows: int = 30,
        repository_id: str | None = None,
    ) -> dict[str, Any]:
        if not session_id.strip():
            raise ValueError("Terminal session_id is required")

        repo_path = self._require_repo_path(repository_id)

        if workspace:
            safe_workspace = self.sandbox.validate_execution_path(
                workspace,
                base_root=repo_path,
            )
        else:
            safe_workspace = repo_path

        managed = await self.agent_terminal_gateway.get_or_create_session(
            session_id=session_id,
            workspace=str(safe_workspace),
            shell=shell,
            cols=cols,
            rows=rows,
            owner=session_id,
            base_root=str(repo_path),
        )

        terminal = managed.terminal

        return {
            "session_id": managed.session_id,
            "workspace": managed.workspace,
            "repository_id": repository_id,
            "pid": terminal.pid,
            "cols": terminal.cols,
            "rows": terminal.rows,
            "alive": terminal.is_alive,
            "persistent": True,
        }

    async def write_terminal_input(
        self,
        session_id: str,
        data: str,
    ) -> dict[str, Any]:
        if not session_id.strip():
            raise ValueError("Terminal session_id is required")

        if not data:
            return {
                "session_id": session_id,
                "status": "empty",
                "bytes_written": 0,
            }

        return await self.agent_terminal_gateway.write(
            session_id=session_id,
            data=data,
            owner=session_id,
        )

    async def interrupt_terminal(self, session_id: str) -> dict[str, Any]:
        if not session_id.strip():
            raise ValueError("Terminal session_id is required")

        return await self.agent_terminal_gateway.interrupt(
            session_id=session_id,
            owner=session_id,
        )

    async def execute_terminal_command(
        self,
        session_id: str,
        command: str,
        timeout_sec: float = 300.0,
    ) -> dict[str, Any]:
        if not session_id.strip():
            raise ValueError("Terminal session_id is required")
        if not command.strip():
            raise ValueError("Terminal command cannot be empty")
        if timeout_sec <= 0:
            raise ValueError("Terminal command timeout must be greater than zero")

        return await self.agent_terminal_gateway.execute_command(
            session_id=session_id,
            command=command,
            owner=session_id,
            timeout=timeout_sec,
        )

    async def run_test(
        self,
        test_path: str | None = None,
        timeout_sec: float = 60.0,
        repository_id: str | None = None,
    ) -> dict[str, Any]:
        repo_path = self._require_repo_path(repository_id)

        safe_test_path = (
            str(
                self.sandbox.validate_safe_path(
                    test_path,
                    base_root=repo_path,
                )
            )
            if test_path
            else None
        )

        return await self.quality_runners.run_pytest(
            test_path=safe_test_path,
            timeout_sec=timeout_sec,
            cwd=repo_path,
            base_root=repo_path,
        )

    async def run_build(
        self,
        command: str | None = None,
        repository_id: str | None = None,
    ) -> dict[str, Any]:
        repo_path = self._require_repo_path(repository_id)

        return await self.quality_runners.run_build(
            command=command,
            cwd=repo_path,
            base_root=repo_path,
        )

    async def run_linter(
        self,
        target_path: str | None = None,
        repository_id: str | None = None,
    ) -> dict[str, Any]:
        repo_path = self._require_repo_path(repository_id)

        safe_target = (
            str(
                self.sandbox.validate_safe_path(
                    target_path,
                    base_root=repo_path,
                )
            )
            if target_path
            else None
        )

        return await self.quality_runners.run_linter(
            target_path=safe_target,
            cwd=repo_path,
            base_root=repo_path,
        )

    async def run_formatter(
        self,
        target_path: str | None = None,
        repository_id: str | None = None,
    ) -> dict[str, Any]:
        repo_path = self._require_repo_path(repository_id)

        safe_target = (
            str(
                self.sandbox.validate_safe_path(
                    target_path,
                    base_root=repo_path,
                )
            )
            if target_path
            else None
        )

        return await self.quality_runners.run_formatter(
            target_path=safe_target,
            cwd=repo_path,
            base_root=repo_path,
        )

    async def run_typecheck(
        self,
        target_path: str | None = None,
        repository_id: str | None = None,
    ) -> dict[str, Any]:
        repo_path = self._require_repo_path(repository_id)

        safe_target = (
            str(
                self.sandbox.validate_safe_path(
                    target_path,
                    base_root=repo_path,
                )
            )
            if target_path
            else None
        )

        return await self.quality_runners.run_typecheck(
            target_path=safe_target,
            cwd=repo_path,
            base_root=repo_path,
        )