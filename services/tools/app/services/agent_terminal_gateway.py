from __future__ import annotations

from typing import Any

from services.tools.app.runtime.pty_runtime import pty_session_manager


class AgentTerminalGateway:
    """
    Gateway for agent access to persistent PTY sessions.

    The gateway uses the same process-level PTY session manager used by the
    terminal WebSocket layer. Repository-scoped sessions may provide an
    explicit base_root, preserving the existing PTY lifecycle while applying
    the selected repository as the security boundary.
    """

    async def execute_command(
        self,
        session_id: str,
        command: str,
        owner: str | None = None,
        timeout: float = 300.0,
    ) -> dict[str, Any]:
        if not session_id:
            raise ValueError("Terminal session_id is required")
        if not command.strip():
            raise ValueError("Terminal command cannot be empty")

        return await pty_session_manager.execute_command(
            session_id=session_id,
            command=command,
            owner=owner,
            timeout=timeout,
        )

    async def get_or_create_session(
        self,
        session_id: str,
        workspace: str,
        shell: str | None = None,
        cols: int = 120,
        rows: int = 30,
        owner: str | None = None,
        base_root: str | None = None,
    ):
        if not session_id:
            raise ValueError("Terminal session_id is required")
        if not workspace:
            raise ValueError("Terminal workspace is required")

        return await pty_session_manager.get_or_create(
            session_id=session_id,
            workspace=workspace,
            shell=shell,
            cols=cols,
            rows=rows,
            owner=owner,
            base_root=base_root,
        )

    async def attach(self, session_id: str, owner: str | None = None):
        return await pty_session_manager.attach(
            session_id=session_id,
            owner=owner,
        )

    async def write(
        self,
        session_id: str,
        data: str,
        owner: str | None = None,
    ) -> dict[str, Any]:
        if not data:
            return {
                "session_id": session_id,
                "status": "empty",
                "bytes_written": 0,
            }

        managed = await self.attach(
            session_id=session_id,
            owner=owner,
        )

        if managed is None:
            raise RuntimeError("Terminal session does not exist")

        try:
            await managed.terminal.write(data)
            return {
                "session_id": session_id,
                "status": "written",
                "bytes_written": len(
                    data.encode("utf-8", errors="replace")
                ),
            }
        finally:
            await pty_session_manager.detach(session_id)

    async def interrupt(
        self,
        session_id: str,
        owner: str | None = None,
    ) -> dict[str, Any]:
        managed = await self.attach(
            session_id=session_id,
            owner=owner,
        )
        if managed is None:
            raise RuntimeError("Terminal session does not exist")

        try:
            await managed.terminal.interrupt()
            return {
                "session_id": session_id,
                "status": "interrupted",
            }
        finally:
            await pty_session_manager.detach(session_id)

    async def send_signal(
        self,
        session_id: str,
        signal_number: int,
        owner: str | None = None,
    ) -> dict[str, Any]:
        managed = await self.attach(
            session_id=session_id,
            owner=owner,
        )
        if managed is None:
            raise RuntimeError("Terminal session does not exist")

        try:
            await managed.terminal.send_signal(signal_number)
            return {
                "session_id": session_id,
                "status": "signal_sent",
                "signal": signal_number,
            }
        finally:
            await pty_session_manager.detach(session_id)

    async def close(self, session_id: str, force: bool = True) -> None:
        await pty_session_manager.remove(
            session_id=session_id,
            force=force,
        )

    async def close_all(self) -> None:
        await pty_session_manager.close_all()