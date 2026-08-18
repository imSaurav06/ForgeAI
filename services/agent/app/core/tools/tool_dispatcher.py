from __future__ import annotations

from typing import Any

import httpx

from services.agent.app.core.patching.patch_normalizer import CanonicalPatch
from services.gateway.app.core.internal_auth import InternalAuthManager
from shared.config.settings import get_settings
from shared.exceptions.handlers import ValidationException
from shared.logging.logger import logger


class AgentToolDispatcher:
    """
    Executes real tool operations across ForgeAI microservices (Tools:8005, Retrieval:8004, Git:8006, Repository:8003).

    Zero synthetic or mocked execution. Every call delegates with internal service authentication
    and returns verified workspace results.
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self.auth_manager = InternalAuthManager()

    def _get_headers(self) -> dict[str, str]:
        token = self.auth_manager.generate_internal_token("agent-service")
        return {
            "X-Internal-Service-Token": token,
            "X-User-ID": "agent_system",
            "X-User-Role": "admin",
        }

    async def read_file(
        self,
        repository_id: str,
        path: str,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> dict[str, Any]:
        """Read text content from a target workspace file."""
        if not path or not path.strip():
            raise ValidationException(message="File path is required for read_file")

        tools_url = self.settings.tool_service_url.rstrip("/")
        endpoint = f"{tools_url}/internal/v1/tools/read-file"
        payload = {
            "repository_id": repository_id,
            "path": path.strip().replace("\\", "/"),
            "start_line": start_line,
            "end_line": end_line,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(endpoint, json=payload, headers=self._get_headers())
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", data)

    async def write_file(
        self,
        repository_id: str,
        path: str,
        content: str,
    ) -> dict[str, Any]:
        """Write content directly to a target workspace file."""
        if not path or not path.strip():
            raise ValidationException(message="File path is required for write_file")

        tools_url = self.settings.tool_service_url.rstrip("/")
        endpoint = f"{tools_url}/internal/v1/tools/write-file"
        payload = {
            "repository_id": repository_id,
            "path": path.strip().replace("\\", "/"),
            "content": content,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(endpoint, json=payload, headers=self._get_headers())
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", data)

    async def search_files(
        self,
        repository_id: str,
        pattern: str,
        path: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search text/regex occurrences in workspace files."""
        if not pattern or not pattern.strip():
            raise ValidationException(message="Search pattern is required")

        tools_url = self.settings.tool_service_url.rstrip("/")
        endpoint = f"{tools_url}/internal/v1/tools/search"
        payload = {
            "repository_id": repository_id,
            "pattern": pattern.strip(),
            "path": path.strip().replace("\\", "/") if path else None,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(endpoint, json=payload, headers=self._get_headers())
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", data)

    async def delete_file(
        self,
        repository_id: str,
        path: str,
    ) -> dict[str, Any]:
        """Delete a file from the target workspace."""
        if not path or not path.strip():
            raise ValidationException(message="File path is required for delete_file")

        tools_url = self.settings.tool_service_url.rstrip("/")
        endpoint = f"{tools_url}/internal/v1/tools/delete-file"
        payload = {
            "repository_id": repository_id,
            "path": path.strip().replace("\\", "/"),
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(endpoint, json=payload, headers=self._get_headers())
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", data)

    async def apply_patch(
        self,
        repository_id: str,
        patch: CanonicalPatch | dict[str, Any],
    ) -> dict[str, Any]:
        """Apply canonical atomic multi-file patch via PatchEngine."""
        tools_url = self.settings.tool_service_url.rstrip("/")
        endpoint = f"{tools_url}/internal/v1/tools/apply-patch"

        if isinstance(patch, CanonicalPatch):
            payload = patch.to_dict(repository_id)
        else:
            payload = {
                "repository_id": repository_id,
                "files_to_create": patch.get("files_to_create", []),
                "files_to_modify": patch.get("files_to_modify", []),
                "files_to_delete": patch.get("files_to_delete", []),
            }

        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(endpoint, json=payload, headers=self._get_headers())
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", data)

    async def run_command(
        self,
        repository_id: str,
        command: str,
        cwd: str | None = None,
        timeout_sec: float = 60.0,
    ) -> dict[str, Any]:
        """Execute a sandboxed shell command inside target workspace."""
        if not command or not command.strip():
            raise ValidationException(message="Command cannot be empty")

        tools_url = self.settings.tool_service_url.rstrip("/")
        endpoint = f"{tools_url}/internal/v1/tools/run-command"
        payload = {
            "repository_id": repository_id,
            "command": command.strip(),
            "cwd": cwd,
            "timeout_sec": timeout_sec,
        }

        async with httpx.AsyncClient(timeout=timeout_sec + 10.0) as client:
            resp = await client.post(endpoint, json=payload, headers=self._get_headers())
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", data)

    async def run_test(
        self,
        repository_id: str,
        test_path: str | None = None,
        timeout_sec: float = 60.0,
    ) -> dict[str, Any]:
        """Execute pytest test runner inside target workspace."""
        tools_url = self.settings.tool_service_url.rstrip("/")
        endpoint = f"{tools_url}/internal/v1/tools/run-test"
        payload = {
            "repository_id": repository_id,
            "test_path": test_path,
            "timeout_sec": timeout_sec,
        }

        async with httpx.AsyncClient(timeout=timeout_sec + 10.0) as client:
            resp = await client.post(endpoint, json=payload, headers=self._get_headers())
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", data)

    async def retrieval_search(
        self,
        repository_id: str,
        query: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Query vector database for semantic code context."""
        retrieval_url = self.settings.retrieval_service_url.rstrip("/")
        endpoint = f"{retrieval_url}/v1/search/semantic"
        payload = {
            "repository_id": repository_id,
            "query": query,
            "limit": limit,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(endpoint, json=payload, headers=self._get_headers())
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", data)

    async def git_status(self, repository_id: str) -> dict[str, Any]:
        """Retrieve git working tree status."""
        git_url = self.settings.git_service_url.rstrip("/")
        endpoint = f"{git_url}/v1/git/status"
        params = {"repo_id": repository_id}

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(endpoint, params=params, headers=self._get_headers())
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", data)

    async def git_diff(self, repository_id: str) -> dict[str, Any]:
        """Retrieve unified git diff."""
        git_url = self.settings.git_service_url.rstrip("/")
        endpoint = f"{git_url}/v1/git/diff"
        params = {"repo_id": repository_id}

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(endpoint, params=params, headers=self._get_headers())
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", data)

    async def git_log(self, repository_id: str, limit: int = 10) -> list[dict[str, Any]]:
        """Retrieve recent git commit history."""
        git_url = self.settings.git_service_url.rstrip("/")
        endpoint = f"{git_url}/v1/git/log"
        params = {"repo_id": repository_id, "limit": limit}

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(endpoint, params=params, headers=self._get_headers())
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", data)

    async def execute_tool(
        self,
        tool_name: str,
        repository_id: str,
        arguments: dict[str, Any],
    ) -> Any:
        """
        Generic dispatch interface mapping action names to microservice tool methods.
        Enforces fail-closed validation on unknown tools.
        """
        clean_name = tool_name.strip().lower()
        logger.info(f"Agent tool dispatch: executing tool '{clean_name}' for repo '{repository_id}'")

        if clean_name in ("read_file", "file_reader", "read"):
            return await self.read_file(
                repository_id=repository_id,
                path=str(arguments.get("path", "")),
                start_line=arguments.get("start_line"),
                end_line=arguments.get("end_line"),
            )

        if clean_name in ("write_file", "create_file", "file_writer", "write"):
            return await self.write_file(
                repository_id=repository_id,
                path=str(arguments.get("path", "")),
                content=str(arguments.get("content", "")),
            )

        if clean_name in ("search_files", "search", "file_search"):
            return await self.search_files(
                repository_id=repository_id,
                pattern=str(arguments.get("pattern", arguments.get("query", ""))),
                path=arguments.get("path"),
            )

        if clean_name in ("delete_file", "delete", "file_deleter"):
            return await self.delete_file(
                repository_id=repository_id,
                path=str(arguments.get("path", "")),
            )

        if clean_name in ("apply_patch", "patch", "patch_engine"):
            raw_patch = arguments.get("patch", arguments)
            return await self.apply_patch(
                repository_id=repository_id,
                patch=raw_patch,
            )

        if clean_name in ("run_command", "terminal", "terminal_command", "exec"):
            return await self.run_command(
                repository_id=repository_id,
                command=str(arguments.get("command", "")),
                cwd=arguments.get("cwd"),
                timeout_sec=float(arguments.get("timeout_sec", 60.0)),
            )

        if clean_name in ("run_test", "test_runner", "pytest", "test"):
            return await self.run_test(
                repository_id=repository_id,
                test_path=arguments.get("test_path"),
                timeout_sec=float(arguments.get("timeout_sec", 60.0)),
            )

        if clean_name in ("retrieval_search", "semantic_search", "rag"):
            return await self.retrieval_search(
                repository_id=repository_id,
                query=str(arguments.get("query", arguments.get("instruction", ""))),
                limit=int(arguments.get("limit", 5)),
            )

        if clean_name in ("git_status", "status"):
            return await self.git_status(repository_id=repository_id)

        if clean_name in ("git_diff", "diff"):
            return await self.git_diff(repository_id=repository_id)

        if clean_name in ("git_log", "log"):
            return await self.git_log(
                repository_id=repository_id,
                limit=int(arguments.get("limit", 10)),
            )

        raise ValidationException(
            message=f"Unknown or unsupported tool action: '{tool_name}'"
        )
