import asyncio
import json
import os
import signal
from contextlib import suppress
from uuid import uuid4

import httpx
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from services.gateway.app.core.internal_auth import (
    verify_internal_service_request,
)
from services.tools.app.runtime.pty_runtime import (
    pty_session_manager,
)

from shared.config.settings import get_settings
from shared.logging.logger import logger


ws_router = APIRouter(tags=["Terminal WebSocket"])



MAX_MESSAGE_BYTES = 64 * 1024
MAX_INPUT_BYTES = 32 * 1024

MIN_TERMINAL_DIMENSION = 1
MAX_TERMINAL_COLUMNS = 500
MAX_TERMINAL_ROWS = 500

ALLOWED_SIGNALS = {
    "SIGINT": signal.SIGINT,
    "SIGTERM": signal.SIGTERM,
}

for _signal_name in (
    "SIGQUIT",
    "SIGTSTP",
    "SIGCONT",
    "SIGBREAK",
):
    _signal_value = getattr(
        signal,
        _signal_name,
        None,
    )

    if _signal_value is not None:
        ALLOWED_SIGNALS[_signal_name] = _signal_value


def _resolve_session_workspace(
    session_id: str,
) -> str | None:
    if not session_id or session_id == "default":
        return None

    # 1. Try In-Process Repository Service
    try:
        from services.repository.app.services.repository_service import (
            RepositoryService,
        )

        repo_svc = RepositoryService()
        meta = repo_svc.get_repository_metadata(session_id)
        if meta and meta.path and os.path.isdir(meta.path):
            return meta.path
    except Exception:
        pass

    # 2. Try MongoDB directly
    try:
        import pymongo
        settings = get_settings()
        client = pymongo.MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=1000)
        db = client[settings.mongodb_database]
        doc = db["repositories"].find_one({"id": session_id})
        if doc and doc.get("path") and os.path.isdir(doc["path"]):
            return doc["path"]
    except Exception:
        pass

    # 3. Try HTTP Repository Service Endpoint
    try:
        from services.gateway.app.core.internal_auth import InternalAuthManager
        auth_mgr = InternalAuthManager()
        token = auth_mgr.generate_internal_token("tools-service")
        headers = {"X-Internal-Service-Token": token}
    except Exception:
        headers = {}

    settings = get_settings()
    candidate_urls = [
        f"{settings.repository_service_url.rstrip('/')}/v1/repositories/{session_id}/status",
        f"http://127.0.0.1:8003/v1/repositories/{session_id}/status",
        f"http://repository:8003/v1/repositories/{session_id}/status",
    ]

    for url in candidate_urls:
        try:
            resp = httpx.get(url, headers=headers, timeout=1.5)
            if resp.status_code == 200:
                data = resp.json().get("data", {})
                path = data.get("path")
                if path and os.path.isdir(path):
                    return path
        except Exception:
            continue

    return None


def _safe_terminal_size(
    value: object,
    default: int,
    maximum: int,
) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default

    return max(
        MIN_TERMINAL_DIMENSION,
        min(parsed, maximum),
    )


def _signal_from_name(
    value: object,
) -> int | None:
    if not isinstance(value, str):
        return None

    normalized = value.strip().upper()

    if not normalized.startswith("SIG"):
        normalized = f"SIG{normalized}"

    return ALLOWED_SIGNALS.get(
        normalized
    )


def _message_size_bytes(
    message: str,
) -> int:
    return len(
        message.encode(
            "utf-8",
            errors="replace",
        )
    )


def _input_size_valid(
    data: str,
) -> bool:
    return (
        len(
            data.encode(
                "utf-8",
                errors="replace",
            )
        )
        <= MAX_INPUT_BYTES
    )


# async def _send_json(
#     websocket: WebSocket,
#     payload: dict[str, object],
# ) -> bool:
#     try:
#         await websocket.send_json(payload)
#         return True
#     except Exception:
#         return False



async def _send_json(
    websocket: WebSocket,
    payload: dict[str, object],
) -> bool:
    try:
        await websocket.send_json(payload)
        logger.info(
            "Terminal WS send_json success "
            f"event={payload.get('event')}"
        )
        return True
    except Exception as err:
        logger.exception(
            "Terminal WS send_json failed "
            f"event={payload.get('event')}: {err}"
        )
        return False
        



async def _send_protocol_error(
    websocket: WebSocket,
    session_id: str,
    code: str,
    message: str,
) -> bool:
    return await _send_json(
        websocket,
        {
            "event": "error",
            "code": code,
            "text": message,
            "session_id": session_id,
        },
    )


@ws_router.websocket(
    "/v1/ws/terminal/{session_id}"
)
async def terminal_websocket(
    websocket: WebSocket,
    session_id: str,
) -> None:
    """
    Real interactive PTY terminal WebSocket session.

    The WebSocket connection is separate from the persistent PTY
    lifecycle.

    PTY output is owned by PTYSessionManager and delivered through
    a bounded per-client subscriber queue.

    On reconnect, buffered terminal output is explicitly marked as
    replay output before live PTY output begins.
    """

    internal_token = websocket.headers.get(
        "X-Internal-Service-Token"
    )

    try:
        verify_internal_service_request(
            internal_token
        )

    except Exception as err:
        logger.warning(
            "Rejected unauthenticated terminal WS "
            f"session {session_id}: {err}"
        )

        with suppress(Exception):
            await websocket.close(
                code=1008,
                reason="Unauthorized terminal session",
            )

        return

    existing_managed = await pty_session_manager.get(
        session_id
    )

    if existing_managed is not None:
        workspace_root = existing_managed.workspace
        base_root = (
            str(existing_managed.terminal.execution_root)
            if existing_managed.terminal.execution_root
            else existing_managed.workspace
        )

    else:
        repo_workspace = _resolve_session_workspace(
            session_id
        )

        if repo_workspace:
            workspace_root = repo_workspace
            base_root = repo_workspace

        else:
            settings = get_settings()

            workspace_root = str(
                settings.workspace_root
            )
            base_root = None

            if not os.path.isdir(workspace_root):
                await websocket.close(
                    code=1011,
                    reason="Terminal workspace unavailable",
                )
                return

    await websocket.accept()

    logger.info(
        "Terminal PTY WS session "
        f"{session_id} opened, "
        f"workspace={workspace_root}"
    )

    initial_cols = 120
    initial_rows = 30

    managed = None
    session = None

    subscriber_id = (
        f"{session_id}:{uuid4().hex}"
    )

    output_queue = None
    replay_count = 0

    try:
        logger.info(
            "Terminal WS creating/getting PTY session "
            f"session={session_id} "
            f"workspace={workspace_root}"
        )

        managed = await pty_session_manager.get_or_create(
            session_id=session_id,
            workspace=workspace_root,
            shell=os.environ.get("SHELL"),
            cols=initial_cols,
            rows=initial_rows,
            owner=session_id,
            base_root=base_root,
        )

        logger.info(
            "Terminal WS PTY get_or_create completed "
            f"session={session_id} "
            f"pid={managed.terminal.pid} "
            f"alive={managed.terminal.is_alive}"
        )

        attached = await pty_session_manager.attach(
            session_id=session_id,
            owner=session_id,
        )

        if attached is None:
            with suppress(Exception):
                await websocket.close(
                    code=1011,
                    reason="Terminal session unavailable",
                )

            return

        managed = attached
        session = managed.terminal

        logger.info(
            "Terminal WS PTY attached "
            f"session={session_id} "
            f"pid={session.pid} "
            f"alive={session.is_alive}"
        )

        # output_queue = await pty_session_manager.subscribe(
        #     session_id=session_id,
        #     subscriber_id=subscriber_id,
        # )
        # try:
        #     output_queue = await pty_session_manager.subscribe(
        #         session_id=session_id,
        #         subscriber_id=subscriber_id,
        #     )

        #     logger.info(
        #         "Terminal WS subscribe completed "
        #         f"session={session_id} "
        #         f"queue_created={output_queue is not None}"
        #     )

        # except asyncio.CancelledError:
        #     logger.exception(
        #         "Terminal WS subscribe CANCELLED "
        #         f"session={session_id}"
        #     )
            # raise



        try:
            output_queue = await pty_session_manager.subscribe(
                session_id=session_id,
                subscriber_id=subscriber_id,
            )

            logger.info(
                "Terminal WS subscribe completed "
                f"session={session_id} "
                f"queue_created={output_queue is not None}"
            )

            if output_queue is None:
                logger.error(
                    "Terminal WS subscribe returned None "
                    f"session={session_id} "
                    f"subscriber_id={subscriber_id}"
                )

                managed_after_subscribe = await pty_session_manager.get(
                    session_id
                )

                logger.error(
                    "Terminal WS session state after failed subscribe "
                    f"session={session_id} "
                    f"exists={managed_after_subscribe is not None} "
                    f"alive={getattr(getattr(managed_after_subscribe, 'terminal', None), 'is_alive', None)}"
                )

                raise RuntimeError(
                    f"Unable to subscribe to PTY session '{session_id}'"
                )

            logger.info(
                "Terminal WS subscribe completed "
                f"session={session_id} "
                f"queue_created=True"
            )

        except asyncio.CancelledError:
            logger.exception(
                "Terminal WS subscribe CANCELLED "
                f"session={session_id}"
            )
            raise

        except Exception as err:
                logger.exception(
                    "Terminal WS subscribe FAILED "
                    f"session={session_id}: {err}"
                )
                raise

        if output_queue is None:
            with suppress(Exception):
                await websocket.close(
                    code=1011,
                    reason="Terminal output unavailable",
                )

            return

        replay_count = output_queue.qsize()

        logger.info(
            "Terminal WS subscriber created "
            f"session={session_id} "
            f"queue_size={replay_count}"
        )

        logger.info(
            "Terminal WS preparing connected event "
            f"session={session_id} "
            f"pid={session.pid if session else None} "
            f"alive={session.is_alive if session else None} "
            f"queue={output_queue is not None}"
        )

        connected = await _send_json(
            websocket,
            {
                "event": "connected",
                "message": (
                    "Terminal connected — "
                    f"workspace: {managed.workspace}"
                ),
                "session_id": session_id,
                "terminal": {
                    "type": "pty",
                    "cols": session.cols,
                    "rows": session.rows,
                    "pid": session.pid,
                    "persistent": True,
                },
                "replay": replay_count > 0,
            },
        )

        if not connected:
            logger.warning(
                "Terminal WS connected event could not be sent "
                f"session={session_id}"
            )
            return

        async def stream_replay() -> bool:
            if replay_count <= 0:
                return True

            started = await _send_json(
                websocket,
                {
                    "event": "replay_start",
                    "session_id": session_id,
                    "chunks": replay_count,
                },
            )

            if not started:
                return False

            for _ in range(replay_count):
                chunk = await output_queue.get()

                if not chunk:
                    continue

                text = chunk.decode(
                    "utf-8",
                    errors="replace",
                )

                sent = await _send_json(
                    websocket,
                    {
                        "event": "output",
                        "text": text,
                        "stream": "stdout",
                        "session_id": session_id,
                        "replay": True,
                    },
                )

                if not sent:
                    return False

            ended = await _send_json(
                websocket,
                {
                    "event": "replay_end",
                    "session_id": session_id,
                },
            )

            return ended

        replay_completed = await stream_replay()

        if not replay_completed:
            return

        async def stream_output() -> None:
            while True:
                chunk = await output_queue.get()

                if not chunk:
                    continue

                text = chunk.decode(
                    "utf-8",
                    errors="replace",
                )

                sent = await _send_json(
                    websocket,
                    {
                        "event": "output",
                        "text": text,
                        "stream": "stdout",
                        "session_id": session_id,
                        "replay": False,
                    },
                )

                if not sent:
                    return

                await pty_session_manager.touch(
                    session_id
                )

        async def monitor_session() -> None:
            while True:
                if session is None:
                    return

                if not session.is_alive:
                    await _send_json(
                        websocket,
                        {
                            "event": "exit",
                            "exit_code": session.exit_status,
                            "signal": session.signal_status,
                            "session_id": session_id,
                        },
                    )

                    return

                overflowed = (
                    await pty_session_manager
                    .subscriber_overflowed(
                        session_id,
                        subscriber_id,
                    )
                )

                if overflowed:
                    await _send_protocol_error(
                        websocket,
                        session_id,
                        "OUTPUT_BACKPRESSURE",
                        (
                            "Terminal client is too slow "
                            "to consume PTY output."
                        ),
                    )

                    with suppress(Exception):
                        await websocket.close(
                            code=1008,
                            reason="Terminal output backpressure",
                        )

                    return

                await asyncio.sleep(0.25)

        async def handle_message(
            message: str,
        ) -> None:
            if not message:
                return

            if (
                _message_size_bytes(message)
                > MAX_MESSAGE_BYTES
            ):
                await _send_protocol_error(
                    websocket,
                    session_id,
                    "MESSAGE_TOO_LARGE",
                    (
                        "Terminal message exceeds the "
                        "maximum allowed size."
                    ),
                )

                with suppress(Exception):
                    await websocket.close(
                        code=1009,
                        reason="Terminal message too large",
                    )

                return

            await pty_session_manager.touch(
                session_id
            )

            try:
                parsed = json.loads(message)

            except json.JSONDecodeError:
                await _send_protocol_error(
                    websocket,
                    session_id,
                    "INVALID_JSON",
                    "Terminal message must contain valid JSON.",
                )
                return

            if not isinstance(parsed, dict):
                await _send_protocol_error(
                    websocket,
                    session_id,
                    "INVALID_MESSAGE",
                    "Terminal message must be a JSON object.",
                )
                return

            message_type = parsed.get("type")

            if not isinstance(
                message_type,
                str,
            ):
                await _send_protocol_error(
                    websocket,
                    session_id,
                    "MISSING_MESSAGE_TYPE",
                    "Terminal message requires a string 'type'.",
                )
                return

            message_type = message_type.strip().lower()

            if message_type == "input":
                data = parsed.get(
                    "data",
                    "",
                )

                if not isinstance(data, str):
                    await _send_protocol_error(
                        websocket,
                        session_id,
                        "INVALID_INPUT",
                        "Terminal input data must be a string.",
                    )
                    return

                if not data:
                    return

                if not _input_size_valid(data):
                    await _send_protocol_error(
                        websocket,
                        session_id,
                        "INPUT_TOO_LARGE",
                        (
                            "Terminal input exceeds the "
                            "maximum allowed size."
                        ),
                    )
                    return

                await session.write(data)
                return

            if message_type == "resize":
                raw_cols = parsed.get("cols")
                raw_rows = parsed.get("rows")

                if (
                    not isinstance(raw_cols, int)
                    or isinstance(raw_cols, bool)
                    or not isinstance(raw_rows, int)
                    or isinstance(raw_rows, bool)
                ):
                    await _send_protocol_error(
                        websocket,
                        session_id,
                        "INVALID_RESIZE",
                        (
                            "Terminal resize requires integer "
                            "cols and rows."
                        ),
                    )
                    return

                cols = _safe_terminal_size(
                    raw_cols,
                    session.cols,
                    MAX_TERMINAL_COLUMNS,
                )

                rows = _safe_terminal_size(
                    raw_rows,
                    session.rows,
                    MAX_TERMINAL_ROWS,
                )

                await session.resize(
                    cols=cols,
                    rows=rows,
                )

                return

            if message_type == "signal":
                signal_value = _signal_from_name(
                    parsed.get("signal")
                )

                if signal_value is None:
                    await _send_protocol_error(
                        websocket,
                        session_id,
                        "INVALID_SIGNAL",
                        "Unsupported terminal signal.",
                    )
                    return

                await session.send_signal(
                    signal_value
                )

                return

            if message_type == "interrupt":
                await session.interrupt()
                return

            if message_type == "eof":
                await session.send_eof()
                return

            if message_type == "ping":
                await _send_json(
                    websocket,
                    {
                        "event": "pong",
                        "session_id": session_id,
                    },
                )
                return

            await _send_protocol_error(
                websocket,
                session_id,
                "UNKNOWN_MESSAGE_TYPE",
                (
                    "Unknown terminal message type: "
                    f"{message_type}"
                ),
            )

        async def receive_client() -> None:
            while True:
                message = await websocket.receive()

                message_type = message.get(
                    "type"
                )

                if message_type == "websocket.disconnect":
                    raise WebSocketDisconnect

                if message_type != "websocket.receive":
                    continue

                text_data = message.get(
                    "text"
                )

                if text_data is None:
                    await _send_protocol_error(
                        websocket,
                        session_id,
                        "BINARY_NOT_SUPPORTED",
                        (
                            "Terminal WebSocket accepts "
                            "text messages only."
                        ),
                    )

                    with suppress(Exception):
                        await websocket.close(
                            code=1003,
                            reason="Text messages required",
                        )

                    return

                await handle_message(
                    text_data
                )

        output_task = asyncio.create_task(
            stream_output(),
            name=(
                f"terminal-output-"
                f"{session_id}-"
                f"{subscriber_id}"
            ),
        )

        input_task = asyncio.create_task(
            receive_client(),
            name=(
                f"terminal-input-"
                f"{session_id}"
            ),
        )

        monitor_task = asyncio.create_task(
            monitor_session(),
            name=(
                f"terminal-monitor-"
                f"{session_id}"
            ),
        )

        done, pending = await asyncio.wait(
            {
                output_task,
                input_task,
                monitor_task,
            },
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in done:
            try:
                await task
            except asyncio.CancelledError:
                logger.info(
                    "Terminal WS task cancelled "
                    f"session={session_id} "
                    f"task={task.get_name()}"
                )
            except WebSocketDisconnect:
                logger.info(
                    "Terminal WS task disconnected "
                    f"session={session_id} "
                    f"task={task.get_name()}"
                )
            except Exception as err:
                logger.exception(
                    "Terminal WS task failed "
                    f"session={session_id} "
                    f"task={task.get_name()}: {err}"
                )

        for task in pending:
            task.cancel()

        if pending:
            await asyncio.gather(
                *pending,
                return_exceptions=True,
            )

    except WebSocketDisconnect:
        logger.info(
            "Terminal PTY WS session "
            f"{session_id} client disconnected"
        )

    except asyncio.CancelledError:
        logger.info(
            "Terminal PTY WS session "
            f"{session_id} cancelled"
        )
        raise

    except PermissionError as err:
        logger.warning(
            "PTY session ownership rejected "
            f"for {session_id}: {err}"
        )

        with suppress(Exception):
            await _send_protocol_error(
                websocket,
                session_id,
                "SESSION_OWNERSHIP_ERROR",
                (
                    "Terminal session ownership "
                    "validation failed."
                ),
            )

    except Exception as err:
        logger.exception(
            "Terminal PTY session "
            f"{session_id} error: {err}"
        )

        with suppress(Exception):
            await _send_protocol_error(
                websocket,
                session_id,
                "TERMINAL_SESSION_ERROR",
                f"Terminal session error: {err}",
            )

    finally:
        if output_queue is not None:
            await pty_session_manager.unsubscribe(
                session_id=session_id,
                subscriber_id=subscriber_id,
            )

        await pty_session_manager.detach(
            session_id
        )

        with suppress(Exception):
            await websocket.close()

        logger.info(
            "Terminal PTY WS session "
            f"{session_id} detached"
        )