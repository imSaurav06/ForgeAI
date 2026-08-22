import asyncio
import websockets

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from shared.logging.logger import logger
from services.gateway.app.core.service_registry import get_service_registry
from services.gateway.app.core.internal_auth import InternalAuthManager
from services.gateway.app.api.dependencies.auth import decode_and_verify_jwt_token

router = APIRouter(prefix="/ws", tags=["WebSockets"])

@router.websocket("/agent/{run_id}")
@router.websocket("/terminal/{session_id}")
async def websocket_endpoint(websocket: WebSocket, run_id: str = "default", session_id: str = None, token: str = None):
    """
    WebSocket endpoint proxy for real-time bidirectional terminal and agent workflow communication.
    """
    target_id = session_id or run_id
    service_name = "tools" if session_id else "agent"
    path = f"/v1/ws/terminal/{target_id}" if session_id else f"/v1/ws/agent/{target_id}"
    
    user_id, role = None, None
    if token:
        try:
            payload = decode_and_verify_jwt_token(token)
            user_id = payload.get("sub") or payload.get("user_id")
            role = payload.get("role", "user")
        except Exception as e:
            logger.warning(f"Invalid token for WebSocket connection: {e}")
            await websocket.close(code=1008)
            return
    else:
        logger.warning("No token provided for WebSocket connection")
        await websocket.close(code=1008)
        return

    await websocket.accept()
    logger.info(f"WebSocket client connected for session/run {target_id}")
    await websocket.send_json({"event": "connected", "run_id": target_id, "status": "active"})
    
    registry = get_service_registry()
    target_base = registry.get_service_url(service_name)
    ws_url = target_base.replace("http://", "ws://").replace("https://", "wss://").rstrip("/") + path
    
    headers = {}
    InternalAuthManager().inject_internal_headers(headers, user_id=user_id, user_role=role)
    
    try:
        async with websockets.connect(ws_url, additional_headers=headers) as upstream_ws:
            async def forward_to_upstream():
                try:
                    while True:
                        data = await websocket.receive_text()
                        await upstream_ws.send(data)
                except WebSocketDisconnect:
                    pass
                except Exception as e:
                    logger.error(f"Client to upstream error: {e}")

            async def forward_to_client():
                try:
                    while True:
                        data = await upstream_ws.recv()
                        await websocket.send_text(data)
                except websockets.exceptions.ConnectionClosed:
                    pass
                except Exception as e:
                    logger.error(f"Upstream to client error: {e}")

            await asyncio.gather(
                forward_to_upstream(),
                forward_to_client()
            )
    except Exception as err:
        logger.info(f"WebSocket direct mode for session {target_id}: {err}")
        try:
            while True:
                msg = await websocket.receive_text()
                await websocket.send_json({"event": "ack", "run_id": target_id, "received": msg})
        except (WebSocketDisconnect, Exception):
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass

