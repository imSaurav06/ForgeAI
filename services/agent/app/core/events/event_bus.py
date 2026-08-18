import asyncio
import time
from collections import defaultdict
from collections.abc import AsyncGenerator
from typing import Any

from pydantic import BaseModel, Field

from shared.logging.logger import logger


class AgentEvent(BaseModel):
    """Event frame emitted during agent run execution."""

    run_id: str = Field(..., description="Target run ID")
    event_type: str = Field(..., description="Event type name e.g. agent.started, patch.generated")
    payload: dict[str, Any] = Field(default_factory=dict, description="Event data payload")
    timestamp: float = Field(default_factory=time.time, description="Emission epoch timestamp")


class AgentEventBus:
    """In-memory event bus managing agent run events and subscriptions."""

    def __init__(self) -> None:
        self._events: dict[str, list[AgentEvent]] = defaultdict(list)
        self._subscribers: dict[str, list[asyncio.Queue[AgentEvent]]] = defaultdict(list)

    def emit(self, run_id: str, event_type: str, payload: dict[str, Any] | None = None) -> AgentEvent:
        """Publish event for a specific run_id."""
        event = AgentEvent(
            run_id=run_id,
            event_type=event_type,
            payload=payload or {},
        )
        self._events[run_id].append(event)
        
        # Notify subscribers
        for q in self._subscribers[run_id]:
            q.put_nowait(event)
            
        logger.info(f"Agent Event [{event_type}] emitted for run_id '{run_id}'")
        return event

    def get_events(self, run_id: str) -> list[AgentEvent]:
        """Retrieve all events emitted for a run_id."""
        return list(self._events.get(run_id, []))

    async def subscribe(self, run_id: str) -> "AsyncGenerator[AgentEvent, None]":
        """Subscribe to real-time events for a run_id."""
        q: asyncio.Queue[AgentEvent] = asyncio.Queue()
        self._subscribers[run_id].append(q)
        try:
            # Yield historical events first
            for event in self.get_events(run_id):
                yield event
            # Yield future events
            while True:
                event = await q.get()
                yield event
        finally:
            if q in self._subscribers[run_id]:
                self._subscribers[run_id].remove(q)


_event_bus_instance: AgentEventBus | None = None


def get_agent_event_bus() -> AgentEventBus:
    """Accessor for global AgentEventBus."""
    global _event_bus_instance
    if _event_bus_instance is None:
        _event_bus_instance = AgentEventBus()
    return _event_bus_instance
