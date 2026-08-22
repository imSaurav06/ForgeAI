from __future__ import annotations

import asyncio
import re
import time
from pathlib import Path
from collections import deque
from dataclasses import dataclass, field

from services.tools.app.runners.pty_terminal import PTYTerminalSession


@dataclass
class PTYSubscriber:
    subscriber_id: str
    queue: asyncio.Queue[bytes]
    overflowed: bool = False


@dataclass
class ManagedPTYSession:
    session_id: str
    terminal: PTYTerminalSession
    workspace: str
    owner: str | None = None
    connected_clients: int = 0
    last_activity: float = field(
        default_factory=time.monotonic
    )
    subscribers: dict[str, PTYSubscriber] = field(
        default_factory=dict
    )
    overflowed_subscribers: set[str] = field(
        default_factory=set
    )
    scrollback: deque[bytes] = field(
        default_factory=deque
    )
    scrollback_bytes: int = 0
    reader_task: asyncio.Task[None] | None = None

    command_lock: asyncio.Lock = field(
        default_factory=asyncio.Lock
    )


class PTYSessionManager:
    """
    Owns persistent PTY sessions independently from individual
    WebSocket connections.

    One logical session_id maps to one persistent PTY session.

    Alive PTYs are reused across WebSocket reconnects.

    Exited PTYs are never reused.

    The manager owns the single PTY reader and distributes terminal
    output to bounded per-client subscriber queues.

    A bounded scrollback buffer keeps recent terminal output available
    for reconnecting clients without allowing unbounded memory growth.

    Command execution is serialized per PTY session so multiple
    commands cannot concurrently corrupt the same interactive shell.
    """

    DEFAULT_IDLE_TIMEOUT = 15 * 60
    DEFAULT_CLEANUP_INTERVAL = 60
    DEFAULT_OUTPUT_QUEUE_SIZE = 256
    DEFAULT_SCROLLBACK_BYTES = 256 * 1024

    COMMAND_MARKER_PREFIX = "__FORGEAI_COMMAND_COMPLETE_"

    def __init__(
        self,
        idle_timeout: float = DEFAULT_IDLE_TIMEOUT,
        cleanup_interval: float = DEFAULT_CLEANUP_INTERVAL,
        output_queue_size: int = DEFAULT_OUTPUT_QUEUE_SIZE,
        scrollback_bytes: int = DEFAULT_SCROLLBACK_BYTES,
    ) -> None:
        self._sessions: dict[str, ManagedPTYSession] = {}
        self._lock = asyncio.Lock()

        self._idle_timeout = max(
            1.0,
            float(idle_timeout),
        )

        self._cleanup_interval = max(
            1.0,
            float(cleanup_interval),
        )

        self._output_queue_size = max(
            1,
            int(output_queue_size),
        )

        self._scrollback_bytes = max(
            1,
            int(scrollback_bytes),
        )

        self._cleanup_task: asyncio.Task[None] | None = None
        self._stopping = False

    async def get(
        self,
        session_id: str,
    ) -> ManagedPTYSession | None:
        async with self._lock:
            managed = self._sessions.get(
                session_id
            )

            if managed is None:
                return None

            if not managed.terminal.is_alive:
                self._sessions.pop(
                    session_id,
                    None,
                )

                return None

            managed.last_activity = time.monotonic()

            self._ensure_reader_locked(
                managed
            )

            return managed

    async def create(
        self,
        session_id: str,
        workspace: str,
        shell: str | None = None,
        cols: int = 120,
        rows: int = 30,
        owner: str | None = None,
    ) -> ManagedPTYSession:
        stale_session: ManagedPTYSession | None = None

        async with self._lock:
            existing = self._sessions.get(
                session_id
            )

            if existing is not None:
                self._validate_owner(
                    existing,
                    owner,
                )

                if existing.terminal.is_alive:
                    existing.last_activity = (
                        time.monotonic()
                    )

                    self._ensure_reader_locked(
                        existing
                    )

                    return existing

                self._sessions.pop(
                    session_id,
                    None,
                )

                stale_session = existing

        if stale_session is not None:
            await self._close_managed_session(
                stale_session
            )

        terminal = PTYTerminalSession(
            cwd=workspace,
            shell=shell,
            cols=cols,
            rows=rows,
        )

        await terminal.start()

        managed = ManagedPTYSession(
            session_id=session_id,
            terminal=terminal,
            workspace=workspace,
            owner=owner,
        )

        async with self._lock:
            existing = self._sessions.get(
                session_id
            )

            if existing is not None:
                self._validate_owner(
                    existing,
                    owner,
                )

                if existing.terminal.is_alive:
                    await terminal.close(
                        force=True
                    )

                    existing.last_activity = (
                        time.monotonic()
                    )

                    self._ensure_reader_locked(
                        existing
                    )

                    return existing

                self._sessions.pop(
                    session_id,
                    None,
                )

            self._sessions[session_id] = managed

            self._start_reader_locked(
                managed
            )

            return managed

    async def get_or_create(
        self,
        session_id: str,
        workspace: str,
        shell: str | None = None,
        cols: int = 120,
        rows: int = 30,
        owner: str | None = None,
        base_root: str | Path | None = None,
    ) -> ManagedPTYSession:
        stale_session: ManagedPTYSession | None = None

        async with self._lock:
            existing = self._sessions.get(
                session_id
            )

            if existing is not None:
                self._validate_owner(
                    existing,
                    owner,
                )

                if existing.terminal.is_alive:
                    existing.last_activity = (
                        time.monotonic()
                    )

                    self._ensure_reader_locked(
                        existing
                    )

                    return existing

                self._sessions.pop(
                    session_id,
                    None,
                )

                stale_session = existing

        if stale_session is not None:
            await self._close_managed_session(
                stale_session
            )

        terminal = PTYTerminalSession(
            cwd=workspace,
            shell=shell,
            cols=cols,
            rows=rows,
            base_root=base_root,
        )

        await terminal.start()

        managed = ManagedPTYSession(
            session_id=session_id,
            terminal=terminal,
            workspace=workspace,
            owner=owner,
        )

        async with self._lock:
            existing = self._sessions.get(
                session_id
            )

            if existing is not None:
                self._validate_owner(
                    existing,
                    owner,
                )

                if existing.terminal.is_alive:
                    await terminal.close(
                        force=True
                    )

                    existing.last_activity = (
                        time.monotonic()
                    )

                    self._ensure_reader_locked(
                        existing
                    )

                    return existing

                self._sessions.pop(
                    session_id,
                    None,
                )

            self._sessions[session_id] = managed

            self._start_reader_locked(
                managed
            )

            return managed

    async def attach(
        self,
        session_id: str,
        owner: str | None = None,
    ) -> ManagedPTYSession | None:
        stale_session: ManagedPTYSession | None = None

        async with self._lock:
            managed = self._sessions.get(
                session_id
            )

            if managed is None:
                return None

            self._validate_owner(
                managed,
                owner,
            )

            if not managed.terminal.is_alive:
                self._sessions.pop(
                    session_id,
                    None,
                )

                stale_session = managed

            else:
                if managed.owner is None:
                    managed.owner = owner

                managed.connected_clients += 1

                managed.last_activity = (
                    time.monotonic()
                )

                self._ensure_reader_locked(
                    managed
                )

                return managed

        if stale_session is not None:
            await self._close_managed_session(
                stale_session
            )

        return None

    async def detach(
        self,
        session_id: str,
    ) -> None:
        async with self._lock:
            managed = self._sessions.get(
                session_id
            )

            if managed is None:
                return

            managed.connected_clients = max(
                0,
                managed.connected_clients - 1,
            )

            managed.last_activity = (
                time.monotonic()
            )

    async def touch(
        self,
        session_id: str,
    ) -> bool:
        async with self._lock:
            managed = self._sessions.get(
                session_id
            )

            if managed is None:
                return False

            if not managed.terminal.is_alive:
                return False

            managed.last_activity = (
                time.monotonic()
            )

            return True

    async def execute_command(
        self,
        session_id: str,
        command: str,
        owner: str | None = None,
        timeout: float = 300.0,
    ) -> dict[str, object]:
        """
        Execute one command inside an existing persistent PTY shell.

        A unique shell marker is appended after the command. The marker
        contains the command exit status and allows the manager to
        determine when the command has completed without terminating
        the persistent shell.

        Commands are serialized per session.
        """

        if not command.strip():
            raise ValueError(
                "Terminal command cannot be empty"
            )

        timeout_value = max(
            1.0,
            float(timeout),
        )

        managed = await self.get(
            session_id
        )

        if managed is None:
            raise RuntimeError(
                "Terminal session does not exist"
            )

        self._validate_owner(
            managed,
            owner,
        )

        async with managed.command_lock:
            if not managed.terminal.is_alive:
                raise RuntimeError(
                    "Terminal session has exited"
                )

            marker = (
                f"{self.COMMAND_MARKER_PREFIX}"
                f"{id(asyncio.current_task())}_"
                f"{time.monotonic_ns()}__"
            )

            queue = await self.subscribe(
                session_id=session_id,
                subscriber_id=marker,
                replay_scrollback=False,
            )

            if queue is None:
                raise RuntimeError(
                    "Unable to subscribe to terminal output"
                )

            try:
                command_text = command.rstrip("\r\n")

                shell_name = managed.terminal.shell.lower().split("\\")[-1]

                if managed.terminal.backend == "windows":
                    if shell_name in {"cmd.exe", "cmd"}:
                        command_payload = (
                            "@(call ) & "
                            + command_text
                            + "\r\n"
                            + "@echo "
                            + marker
                            + ":%errorlevel%\r\n"
                        )
                    elif shell_name in {"powershell.exe", "powershell", "pwsh.exe", "pwsh"}:
                        command_payload = (
                            "$LASTEXITCODE = 0\r\n"
                            + command_text
                            + "\r\n"
                            + "$__ec = if ($?) { if ($LASTEXITCODE -ne $null -and $LASTEXITCODE -ne 0) { $LASTEXITCODE } else { 0 } } else { if ($LASTEXITCODE -ne $null -and $LASTEXITCODE -ne 0) { $LASTEXITCODE } else { 1 } }\r\n"
                            + "Write-Output \""
                            + marker
                            + ":$__ec\"\r\n"
                        )
                    else:
                        command_payload = (
                            "@(call ) & "
                            + command_text
                            + "\r\n"
                            + "@echo "
                            + marker
                            + ":%errorlevel%\r\n"
                        )
                else:
                    command_payload = (
                        command_text
                        + "\n"
                        + "printf '\\n"
                        + marker
                        + ":%s\\n' $?\n"
                    )

                await managed.terminal.write(
                    command_payload
                )

                deadline = (
                    time.monotonic()
                    + timeout_value
                )

                output = bytearray()

                marker_bytes = marker.encode(
                    "utf-8"
                )

                while True:
                    remaining = (
                        deadline
                        - time.monotonic()
                    )

                    if remaining <= 0:
                        await self._interrupt_command(
                            managed
                        )

                        return {
                            "session_id": session_id,
                            "status": "timeout",
                            "exit_code": None,
                            "output": output.decode(
                                "utf-8",
                                errors="replace",
                            ),
                        }

                    try:
                        chunk = await asyncio.wait_for(
                            queue.get(),
                            timeout=remaining,
                        )

                    except asyncio.TimeoutError:
                        await self._interrupt_command(
                            managed
                        )

                        return {
                            "session_id": session_id,
                            "status": "timeout",
                            "exit_code": None,
                            "output": output.decode(
                                "utf-8",
                                errors="replace",
                            ),
                        }

                    if not chunk:
                        continue

                    output.extend(chunk)

                    marker_position = output.find(
                        marker_bytes
                    )

                    if marker_position == -1:
                        continue

                    marker_match = re.search(
                        re.escape(marker_bytes)
                        + rb":(-?\d+)",
                        output,
                    )

                    if marker_match is None:
                        continue

                    try:
                        exit_code = int(
                            marker_match.group(1)
                        )
                    except ValueError:
                        continue

                    clean_output = output[
                        :marker_position
                    ]

                    return {
                        "session_id": session_id,
                        "status": "completed",
                        "exit_code": exit_code,
                        "output": clean_output.decode(
                            "utf-8",
                            errors="replace",
                        ),
                    }

            finally:
                await self.unsubscribe(
                    session_id=session_id,
                    subscriber_id=marker,
                )

                await self.touch(
                    session_id
                )

    async def _interrupt_command(
        self,
        managed: ManagedPTYSession,
    ) -> None:
        if not managed.terminal.is_alive:
            return

        try:
            await managed.terminal.interrupt()
        except Exception:
            pass

    async def subscribe(
        self,
        session_id: str,
        subscriber_id: str,
        replay_scrollback: bool = True,
    ) -> asyncio.Queue[bytes] | None:
        async with self._lock:
            managed = self._sessions.get(
                session_id
            )

            if managed is None:
                return None

            if not managed.terminal.is_alive:
                return None

            existing = managed.subscribers.get(
                subscriber_id
            )

            if existing is not None:
                return existing.queue

            managed.overflowed_subscribers.discard(
                subscriber_id
            )

            subscriber = PTYSubscriber(
                subscriber_id=subscriber_id,
                queue=asyncio.Queue(
                    maxsize=self._output_queue_size
                ),
            )

            managed.subscribers[
                subscriber_id
            ] = subscriber

            managed.last_activity = (
                time.monotonic()
            )

            if replay_scrollback:
                replay_limit = max(1, subscriber.queue.maxsize - 50) if subscriber.queue.maxsize > 0 else len(managed.scrollback)
                replay_chunks = list(managed.scrollback)[-replay_limit:]
                for chunk in replay_chunks:
                    try:
                        subscriber.queue.put_nowait(
                            chunk
                        )
                    except asyncio.QueueFull:
                        subscriber.overflowed = True
                        managed.overflowed_subscribers.add(
                            subscriber_id
                        )
                        managed.subscribers.pop(
                            subscriber_id,
                            None,
                        )
                        return subscriber.queue

            self._ensure_reader_locked(
                managed
            )

            return subscriber.queue

    async def unsubscribe(
        self,
        session_id: str,
        subscriber_id: str,
    ) -> None:
        async with self._lock:
            managed = self._sessions.get(
                session_id
            )

            if managed is None:
                return

            managed.subscribers.pop(
                subscriber_id,
                None,
            )

            managed.overflowed_subscribers.discard(
                subscriber_id
            )

            managed.last_activity = (
                time.monotonic()
            )

    async def subscriber_overflowed(
        self,
        session_id: str,
        subscriber_id: str,
    ) -> bool:
        async with self._lock:
            managed = self._sessions.get(
                session_id
            )

            if managed is None:
                return False

            if subscriber_id in (
                managed.overflowed_subscribers
            ):
                return True

            subscriber = managed.subscribers.get(
                subscriber_id
            )

            if subscriber is None:
                return False

            return subscriber.overflowed

    async def get_scrollback(
        self,
        session_id: str,
    ) -> bytes:
        async with self._lock:
            managed = self._sessions.get(
                session_id
            )

            if managed is None:
                return b""

            return b"".join(
                managed.scrollback
            )

    async def remove(
        self,
        session_id: str,
        force: bool = True,
    ) -> None:
        async with self._lock:
            managed = self._sessions.pop(
                session_id,
                None,
            )

        if managed is None:
            return

        await self._close_managed_session(
            managed,
            force=force,
        )

    async def cleanup_idle_sessions(self) -> int:
        now = time.monotonic()

        async with self._lock:
            idle_sessions = [
                managed
                for managed in self._sessions.values()
                if (
                    managed.connected_clients == 0
                    and not managed.subscribers
                    and not managed.overflowed_subscribers
                    and (
                        not managed.terminal.is_alive
                        or (
                            now - managed.last_activity
                            >= self._idle_timeout
                        )
                    )
                )
            ]

            for managed in idle_sessions:
                self._sessions.pop(
                    managed.session_id,
                    None,
                )

        if not idle_sessions:
            return 0

        await asyncio.gather(
            *(
                self._close_managed_session(
                    managed
                )
                for managed in idle_sessions
            ),
            return_exceptions=True,
        )

        return len(idle_sessions)

    async def start_cleanup_worker(
        self,
    ) -> None:
        if (
            self._cleanup_task is not None
            and not self._cleanup_task.done()
        ):
            return

        self._stopping = False

        self._cleanup_task = asyncio.create_task(
            self._cleanup_loop(),
            name="pty-session-cleanup",
        )

    async def stop_cleanup_worker(
        self,
    ) -> None:
        self._stopping = True

        task = self._cleanup_task
        self._cleanup_task = None

        if task is None:
            return

        task.cancel()

        try:
            await task

        except asyncio.CancelledError:
            pass

    async def _cleanup_loop(
        self,
    ) -> None:
        while not self._stopping:
            try:
                await asyncio.sleep(
                    self._cleanup_interval
                )

                if self._stopping:
                    break

                await self.cleanup_idle_sessions()

            except asyncio.CancelledError:
                raise

            except Exception:
                continue

    async def close_all(
        self,
    ) -> None:
        await self.stop_cleanup_worker()

        async with self._lock:
            sessions = list(
                self._sessions.values()
            )

            self._sessions.clear()

        if not sessions:
            return

        await asyncio.gather(
            *(
                self._close_managed_session(
                    managed
                )
                for managed in sessions
            ),
            return_exceptions=True,
        )

    async def list_session_ids(
        self,
    ) -> list[str]:
        async with self._lock:
            return list(
                self._sessions.keys()
            )

    async def count(
        self,
    ) -> int:
        async with self._lock:
            return len(self._sessions)

    def _ensure_reader_locked(
      self,
      managed: ManagedPTYSession,
      ) -> None:
        if not managed.terminal.is_alive:
            return

        task = managed.reader_task

        if (
            task is not None
            and not task.done()
        ):
            return

        self._start_reader_locked(
            managed
        )

    def _start_reader_locked(
        self,
        managed: ManagedPTYSession,
    ) -> None:
        if not managed.terminal.is_alive:
            return

        managed.reader_task = asyncio.create_task(
            self._read_pty_output(managed),
            name=(
                f"pty-reader-"
                f"{managed.session_id}"
            ),
        )

    async def _read_pty_output(
        self,
        managed: ManagedPTYSession,
    ) -> None:
        try:
            while not self._stopping:
                chunk = await managed.terminal.read(
                    4096
                )

                if chunk is None:
                    break

                if not chunk:
                    await asyncio.sleep(0)
                    continue

                async with self._lock:
                    if (
                        managed.session_id
                        not in self._sessions
                    ):
                        return

                    self._append_scrollback_locked(
                        managed,
                        chunk,
                    )

                    self._broadcast_output_locked(
                        managed,
                        chunk,
                    )

                    managed.last_activity = (
                        time.monotonic()
                    )

        except asyncio.CancelledError:
            raise

        except Exception:
            pass

    def _append_scrollback_locked(
        self,
        managed: ManagedPTYSession,
        chunk: bytes,
    ) -> None:
        if not chunk:
            return

        if len(chunk) >= self._scrollback_bytes:
            retained = chunk[
                -self._scrollback_bytes:
            ]

            managed.scrollback.clear()

            managed.scrollback.append(
                retained
            )

            managed.scrollback_bytes = len(
                retained
            )

            return

        managed.scrollback.append(
            chunk
        )

        managed.scrollback_bytes += len(
            chunk
        )

        while (
            managed.scrollback
            and managed.scrollback_bytes
            > self._scrollback_bytes
        ):
            removed = managed.scrollback.popleft()

            managed.scrollback_bytes -= len(
                removed
            )

    def _broadcast_output_locked(
        self,
        managed: ManagedPTYSession,
        chunk: bytes,
    ) -> None:
        for subscriber in list(
            managed.subscribers.values()
        ):
            if subscriber.overflowed:
                continue

            try:
                subscriber.queue.put_nowait(
                    chunk
                )

            except asyncio.QueueFull:
                subscriber.overflowed = True

                managed.overflowed_subscribers.add(
                    subscriber.subscriber_id
                )

                managed.subscribers.pop(
                    subscriber.subscriber_id,
                    None,
                )

    async def _stop_reader(
        self,
        managed: ManagedPTYSession,
    ) -> None:
        task = managed.reader_task

        if task is None:
            return

        managed.reader_task = None

        if task.done():
            return

        task.cancel()

        try:
            await task

        except asyncio.CancelledError:
            pass

    async def _close_managed_session(
        self,
        managed: ManagedPTYSession,
        force: bool = True,
    ) -> None:
        await self._stop_reader(
            managed
        )

        await managed.terminal.close(
            force=force
        )

    def _validate_owner(
        self,
        managed: ManagedPTYSession,
        owner: str | None,
    ) -> None:
        """
        Validate PTY session access.

        Persistent PTY sessions are shareable between authorized
        terminal clients such as the WebSocket terminal and the
        agent terminal gateway.

        The owner field remains session metadata, but it is not
        treated as an exclusive ownership lock.
        """
        return
        