import asyncio
from collections import defaultdict

from fastapi import WebSocket

from services.gateway.app.core.metrics import get_metrics_registry
from shared.logging.logger import logger


class WebSocketConnectionManager:
    """WebSocket Connection Manager handling active sockets, reconnection, and event broadcasting."""

    def __init__(self) -> None:
        self.active_connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()
        self.metrics = get_metrics_registry()

    async def connect(self, websocket: WebSocket, run_id: str) -> None:
        """Accept and register a new WebSocket connection for a run_id."""
        await websocket.accept()
        async with self._lock:
            self.active_connections[run_id].add(websocket)
        self.metrics.increment_active_connections()
        logger.info(f"WebSocket client connected for run_id '{run_id}' (Listeners: {len(self.active_connections[run_id])})")

    async def disconnect(self, websocket: WebSocket, run_id: str) -> None:
        """Unregister a disconnected WebSocket connection."""
        async with self._lock:
            if run_id in self.active_connections:
                self.active_connections[run_id].discard(websocket)
                if not self.active_connections[run_id]:
                    del self.active_connections[run_id]
        self.metrics.decrement_active_connections()
        logger.info(f"WebSocket client disconnected for run_id '{run_id}'")

    async def send_personal_message(self, message: dict, websocket: WebSocket) -> None:
        """Send JSON message to a single WebSocket client."""
        await websocket.send_json(message)

    async def broadcast(self, run_id: str, message: dict) -> int:
        """Broadcast JSON message to all WebSocket connections for run_id."""
        connections = list(self.active_connections.get(run_id, set()))
        sent_count = 0

        for connection in connections:
            try:
                await connection.send_json(message)
                sent_count += 1
            except Exception as err:
                logger.warning(f"Error broadcasting WebSocket message to run_id '{run_id}': {err}")
                await self.disconnect(connection, run_id)

        return sent_count

    def get_connection_count(self, run_id: str | None = None) -> int:
        """Get connection count for a specific run_id or total active sockets."""
        if run_id:
            return len(self.active_connections.get(run_id, set()))
        return sum(len(conns) for conns in self.active_connections.values())


_ws_manager_instance: WebSocketConnectionManager | None = None


def get_ws_manager() -> WebSocketConnectionManager:
    """Accessor for global WebSocketConnectionManager."""
    global _ws_manager_instance
    if _ws_manager_instance is None:
        _ws_manager_instance = WebSocketConnectionManager()
    return _ws_manager_instance
