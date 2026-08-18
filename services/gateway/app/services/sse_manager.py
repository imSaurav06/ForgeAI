import asyncio
import json
from collections import defaultdict
from collections.abc import AsyncGenerator

from shared.logging.logger import logger


class SSEConnectionManager:
    """SSE Connection Manager handling subscriptions, heartbeats, and broadcasting by run_id."""

    def __init__(self, heartbeat_interval: float = 15.0) -> None:
        self.heartbeat_interval = heartbeat_interval
        self._connections: dict[str, set[asyncio.Queue]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def subscribe(self, run_id: str) -> AsyncGenerator[str, None]:
        """Subscribe client to SSE event stream for a specific run_id."""
        queue: asyncio.Queue[str] = asyncio.Queue()

        async with self._lock:
            self._connections[run_id].add(queue)

        logger.info(f"SSE client subscribed to run_id: '{run_id}' (Total listeners: {len(self._connections[run_id])})")

        try:
            # Send initial connected event
            connected_evt = f"event: connected\ndata: {json.dumps({'run_id': run_id, 'status': 'connected'})}\n\n"
            yield connected_evt

            while True:
                try:
                    event_data = await asyncio.wait_for(queue.get(), timeout=self.heartbeat_interval)
                    yield event_data
                except TimeoutError:
                    # Send heartbeat frame
                    yield f"event: ping\ndata: {json.dumps({'run_id': run_id, 'type': 'heartbeat'})}\n\n"
        except asyncio.CancelledError:
            logger.info(f"SSE client connection cancelled for run_id: '{run_id}'")
        finally:
            async with self._lock:
                self._connections[run_id].discard(queue)
                if not self._connections[run_id]:
                    del self._connections[run_id]
            logger.info(f"SSE client unsubscribed from run_id: '{run_id}'")

    async def broadcast(self, run_id: str, event_name: str, payload: dict) -> int:
        """Broadcast an SSE event payload to all active subscribers for run_id."""
        formatted_event = f"event: {event_name}\ndata: {json.dumps(payload)}\n\n"
        listeners = self._connections.get(run_id, set())

        count = 0
        for q in list(listeners):
            try:
                q.put_nowait(formatted_event)
                count += 1
            except Exception as err:
                logger.warning(f"Failed broadcasting SSE event to queue on run_id '{run_id}': {err}")

        return count

    def get_listener_count(self, run_id: str) -> int:
        """Return count of active listeners for a run_id."""
        return len(self._connections.get(run_id, set()))


_sse_manager_instance: SSEConnectionManager | None = None


def get_sse_manager() -> SSEConnectionManager:
    """Accessor for global SSEConnectionManager."""
    global _sse_manager_instance
    if _sse_manager_instance is None:
        _sse_manager_instance = SSEConnectionManager()
    return _sse_manager_instance
