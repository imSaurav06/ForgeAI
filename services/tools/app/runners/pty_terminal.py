from __future__ import annotations

import asyncio
import os
import select
import shutil
import signal
from pathlib import Path
from typing import Any, Mapping

import pexpect
from pexpect.exceptions import EOF, TIMEOUT

from services.tools.app.sandbox.security_sandbox import (
    SecuritySandbox,
)


class PTYTerminalSession:
    """
    Persistent interactive PTY-backed shell session.

    Uses:
    - pexpect on POSIX systems
    - pywinpty/ConPTY on Windows

    The public session API is platform independent.
    """

    def __init__(
        self,
        cwd: str | Path,
        env: Mapping[str, str] | None = None,
        shell: str | None = None,
        cols: int = 120,
        rows: int = 30,
        base_root: str | Path | None = None,
    ) -> None:
        self.sandbox = SecuritySandbox()

        self.execution_root = (
            self.sandbox._resolve_base_root(base_root)
            if base_root is not None
            else None
        )

        self.cwd = (
            self.sandbox.validate_execution_path(cwd, self.execution_root)
            if self.execution_root is not None
            else self.sandbox.validate_terminal_workspace(cwd)
        )

        self.cols = max(1, int(cols))
        self.rows = max(1, int(rows))

        self.env = (
            dict(env)
            if env is not None
            else dict(os.environ)
        )

        self.env.setdefault(
            "TERM",
            "xterm-256color",
        )
        self.env.setdefault(
            "COLORTERM",
            "truecolor",
        )

        self._requested_shell = shell

        self._backend = (
            "windows"
            if os.name == "nt"
            else "posix"
        )

        self.shell = self._resolve_shell(
            shell
        )

        self.child: Any = None

        self._write_lock = asyncio.Lock()
        self._close_lock = asyncio.Lock()

        self._started = False
        self._closed = False

        self._exit_status: int | None = None
        self._signal_status: int | None = None

    @property
    def pid(self) -> int | None:
        if self.child is None:
            return None

        return getattr(
            self.child,
            "pid",
            None,
        )

    @property
    def is_alive(self) -> bool:
        if self.child is None:
            return False

        try:
            return bool(
                self.child.isalive()
            )
        except Exception:
            return False

    @property
    def exit_status(self) -> int | None:
        return self._exit_status

    @property
    def signal_status(self) -> int | None:
        return self._signal_status

    @property
    def backend(self) -> str:
        return self._backend

    async def start(self) -> None:
        if self._started:
            return

        if self._closed:
            raise RuntimeError(
                "PTY session has already been closed"
            )

        if self._backend == "windows":
            await self._start_windows()
        else:
            await self._start_posix()

        self._started = True

    async def _start_posix(self) -> None:
        self.child = await asyncio.to_thread(
            pexpect.spawn,
            command=self.shell,
            args=[],
            timeout=30,
            maxread=4096,
            searchwindowsize=None,
            logfile=None,
            cwd=str(self.cwd),
            env=self.env,
            ignore_sighup=True,
            echo=True,
            encoding=None,
            codec_errors="replace",
            dimensions=(
                self.rows,
                self.cols,
            ),
            use_poll=True,
        )

    async def _start_windows(self) -> None:
        try:
            from winpty import PtyProcess
        except ImportError as exc:
            raise RuntimeError(
                "pywinpty is required for Windows PTY support. "
                "Install it with: python -m pip install pywinpty"
            ) from exc

        self.child = await asyncio.to_thread(
            PtyProcess.spawn,
            self.shell,
            dimensions=(
                self.rows,
                self.cols,
            ),
            env=self.env,
            cwd=str(self.cwd),
        )

    async def write(
        self,
        data: str | bytes,
    ) -> None:
        if not data:
            return

        child = self._require_child()

        if not self.is_alive:
            self._capture_exit_status()

            raise RuntimeError(
                "Cannot write to an exited PTY session"
            )

        if isinstance(data, bytes):
            payload = data.decode(
                "utf-8",
                errors="replace",
            )
        else:
            payload = data

        async with self._write_lock:
            if self._backend == "windows":
                await asyncio.to_thread(
                    child.write,
                    payload,
                )
            else:
                await asyncio.to_thread(
                    child.send,
                    payload.encode("utf-8"),
                )

    async def read(
        self,
        max_bytes: int = 4096,
    ) -> bytes | None:
        """
        Read currently available PTY output.

        Returns:
            bytes: available output
            b"": no output currently available
            None: PTY exited / EOF
        """

        child = self._require_child()

        if not self.is_alive:
            self._capture_exit_status()

            if self._backend == "posix":
                buffered = getattr(
                    child,
                    "before",
                    None,
                )

                if buffered:
                    child.before = b""

                    if isinstance(
                        buffered,
                        str,
                    ):
                        return buffered.encode(
                            "utf-8",
                            errors="replace",
                        )

                    return buffered

            return None

        if self._backend == "windows":
            return await self._read_windows(
                child,
                max_bytes,
            )

        return await self._read_posix(
            child,
            max_bytes,
        )

    async def _read_posix(
        self,
        child: Any,
        max_bytes: int,
    ) -> bytes | None:
        try:
            data = await asyncio.to_thread(
                child.read_nonblocking,
                max_bytes,
                0.1,
            )

            if isinstance(
                data,
                str,
            ):
                return data.encode(
                    "utf-8",
                    errors="replace",
                )

            return data

        except TIMEOUT:
            return b""

        except EOF:
            self._capture_exit_status()

            buffered = getattr(
                child,
                "before",
                None,
            )

            if buffered:
                child.before = b""

                if isinstance(
                    buffered,
                    str,
                ):
                    return buffered.encode(
                        "utf-8",
                        errors="replace",
                    )

                return buffered

            return None

        except OSError:
            self._capture_exit_status()
            return None

    async def _read_windows(
        self,
        child: Any,
        max_bytes: int,
    ) -> bytes | None:
        """
        Non-blocking Windows PTY read.

        pywinpty's high-level read() uses a blocking socket
        receive. We therefore poll the underlying socket
        before receiving data.
        """

        fileobj = getattr(
            child,
            "fileobj",
            None,
        )

        if fileobj is None:
            return b""

        try:
            readable, _, _ = await asyncio.to_thread(
                select.select,
                [fileobj],
                [],
                [],
                0.05,
            )

            if not readable:
                if not child.isalive():
                    self._capture_exit_status()
                    return None

                return b""

            data = await asyncio.to_thread(
                fileobj.recv,
                max(1, int(max_bytes)),
            )

            if not data:
                self._capture_exit_status()
                return None

            if isinstance(
                data,
                str,
            ):
                return data.encode(
                    "utf-8",
                    errors="replace",
                )

            return data

        except (
            BlockingIOError,
            TimeoutError,
        ):
            if not child.isalive():
                self._capture_exit_status()
                return None

            return b""

        except (
            ConnectionResetError,
            ConnectionAbortedError,
            BrokenPipeError,
            EOFError,
            OSError,
        ):
            if not child.isalive():
                self._capture_exit_status()
                return None

            return b""

    async def resize(
        self,
        cols: int,
        rows: int,
    ) -> None:
        child = self._require_child()

        cols = max(
            1,
            int(cols),
        )

        rows = max(
            1,
            int(rows),
        )

        self.cols = cols
        self.rows = rows

        if not self.is_alive:
            return

        await asyncio.to_thread(
            self._resize_sync,
            child,
            rows,
            cols,
        )

    def _resize_sync(
        self,
        child: Any,
        rows: int,
        cols: int,
    ) -> None:
        if self._backend == "windows":
            if hasattr(
                child,
                "setwinsize",
            ):
                child.setwinsize(
                    rows,
                    cols,
                )
                return

            if hasattr(
                child,
                "set_size",
            ):
                child.set_size(
                    cols,
                    rows,
                )
                return

            raise RuntimeError(
                "Windows PTY backend does not "
                "support terminal resizing"
            )

        child.setwinsize(
            rows,
            cols,
        )

    async def send_signal(
        self,
        sig: int,
    ) -> None:
        child = self._require_child()

        if not self.is_alive:
            self._capture_exit_status()
            return

        pid = self.pid

        if pid is None:
            return

        try:
            if self._backend == "posix":
                await asyncio.to_thread(
                    os.killpg,
                    pid,
                    sig,
                )
                return

            await self._send_windows_signal(
                child,
                sig,
            )

        except ProcessLookupError:
            self._capture_exit_status()

    async def _send_windows_signal(
        self,
        child: Any,
        sig: int,
    ) -> None:
        if sig == signal.SIGINT:
            if hasattr(
                child,
                "sendintr",
            ):
                try:
                    await asyncio.to_thread(
                        child.sendintr,
                    )
                except Exception:
                    pass

            try:
                await asyncio.to_thread(
                    child.write,
                    "\x03",
                )
            except Exception:
                pass

            pid = self.pid
            if pid is not None:
                try:
                    import psutil
                    proc = psutil.Process(pid)
                    for subproc in proc.children(recursive=True):
                        try:
                            subproc.terminate()
                        except Exception:
                            pass
                except Exception:
                    pass

            return

        if sig in (
            signal.SIGTERM,
            signal.SIGKILL,
        ):
            await asyncio.to_thread(
                child.close,
                True,
            )
            return

        if hasattr(
            signal,
            "SIGBREAK",
        ) and sig == signal.SIGBREAK:
            if hasattr(
                child,
                "sendcontrol",
            ):
                await asyncio.to_thread(
                    child.sendcontrol,
                    "c",
                )
                return

            await asyncio.to_thread(
                child.write,
                "\x03",
            )
            return

        raise ValueError(
            f"Unsupported Windows terminal signal: {sig}"
        )

    async def interrupt(self) -> None:
        await self.send_signal(
            signal.SIGINT
        )

    async def send_eof(self) -> None:
        child = self._require_child()

        if not self.is_alive:
            return

        if self._backend == "windows":
            if hasattr(
                child,
                "sendeof",
            ):
                await asyncio.to_thread(
                    child.sendeof,
                )
                return

            await asyncio.to_thread(
                child.write,
                "\x04",
            )
            return

        await asyncio.to_thread(
            child.sendeof,
        )

    async def wait(self) -> int | None:
        child = self._require_child()

        await asyncio.to_thread(
            child.wait
        )

        self._capture_exit_status()

        return self._exit_status

    async def close(
        self,
        force: bool = True,
    ) -> None:
        async with self._close_lock:
            if self._closed:
                return

            self._closed = True

            child = self.child

            if child is None:
                return

            try:
                if child.isalive():
                    if self._backend == "windows":
                        await asyncio.to_thread(
                            child.close,
                            force,
                        )
                    else:
                        pid = child.pid

                        if (
                            force
                            and pid is not None
                        ):
                            try:
                                await asyncio.to_thread(
                                    os.killpg,
                                    pid,
                                    signal.SIGTERM,
                                )
                            except ProcessLookupError:
                                pass

                            await asyncio.sleep(
                                0.2
                            )

                            if child.isalive():
                                try:
                                    await asyncio.to_thread(
                                        os.killpg,
                                        pid,
                                        signal.SIGKILL,
                                    )
                                except ProcessLookupError:
                                    pass

                        await asyncio.to_thread(
                            child.close,
                            False,
                        )

            except Exception as err:
                try:
                    if child.isalive():
                        if self._backend == "windows":
                            await asyncio.to_thread(
                                child.close,
                                True,
                            )
                        else:
                            pid = child.pid

                            if pid is not None:
                                await asyncio.to_thread(
                                    os.killpg,
                                    pid,
                                    signal.SIGKILL,
                                )
                except Exception:
                    pass

                raise RuntimeError(
                    f"Failed to close PTY session: {err}"
                ) from err

            finally:
                self._capture_exit_status()

    def _capture_exit_status(self) -> None:
        child = self.child

        if child is None:
            return

        self._exit_status = getattr(
            child,
            "exitstatus",
            None,
        )

        self._signal_status = getattr(
            child,
            "signalstatus",
            None,
        )

        if (
            self._exit_status is None
            and self._backend == "windows"
            and not child.isalive()
        ):
            status = getattr(
                child,
                "exit_code",
                None,
            )

            if isinstance(
                status,
                int,
            ):
                self._exit_status = status

    def _require_child(self) -> Any:
        if (
            self.child is None
            or not self._started
        ):
            raise RuntimeError(
                "PTY session has not been started"
            )

        return self.child

    def _resolve_shell(
        self,
        requested_shell: str | None,
    ) -> str:
        if os.name == "nt":
            candidates: list[str] = []

            if requested_shell:
                candidates.append(
                    requested_shell
                )

            comspec = os.environ.get(
                "COMSPEC"
            )

            if comspec:
                candidates.append(
                    comspec
                )

            candidates.extend(
                [
                    "cmd.exe",
                    "powershell.exe",
                    "pwsh.exe",
                ]
            )

            for candidate in candidates:
                resolved = shutil.which(
                    candidate
                )

                if resolved:
                    return resolved

            raise RuntimeError(
                "No supported Windows shell executable was found"
            )

        candidates = []

        if requested_shell:
            candidates.append(
                requested_shell
            )

        environment_shell = os.environ.get(
            "SHELL"
        )

        if environment_shell:
            candidates.append(
                environment_shell
            )

        candidates.extend(
            [
                "/bin/bash",
                "/bin/sh",
            ]
        )

        for candidate in candidates:
            resolved = shutil.which(
                candidate
            )

            if resolved:
                return resolved

        raise RuntimeError(
            "No supported POSIX shell executable was found"
        )