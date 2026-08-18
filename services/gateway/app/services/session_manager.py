import time
from typing import Any

from pydantic import BaseModel, Field

from shared.exceptions.handlers import NotFoundException
from shared.logging.logger import logger


class AgentExecutionSession(BaseModel):
    """Model tracking state of a long-running agent execution session."""

    session_id: str = Field(..., description="Unique session ID (run_id)")
    project_id: str = Field(..., description="Target project workspace ID")
    mode: str = Field(..., description="Agent operating mode (CODE, PLAN, etc.)")
    instruction: str = Field(..., description="User task instruction")
    status: str = Field(default="created", description="Session status")
    created_at: float = Field(default_factory=time.time, description="Creation epoch timestamp")
    updated_at: float = Field(default_factory=time.time, description="Last update epoch timestamp")
    context: dict[str, Any] = Field(default_factory=dict, description="Session state variables")


class GatewaySessionManager:
    """Manager tracking long-running agent execution sessions with expiration cleanup."""

    def __init__(self, session_ttl_seconds: float = 3600.0) -> None:
        self.session_ttl_seconds = session_ttl_seconds
        self._sessions: dict[str, AgentExecutionSession] = {}

    def create_session(self, run_id: str, project_id: str, mode: str, instruction: str) -> AgentExecutionSession:
        """Initialize a new agent execution session."""
        session = AgentExecutionSession(
            session_id=run_id,
            project_id=project_id,
            mode=mode,
            instruction=instruction,
            status="started",
        )
        self._sessions[run_id] = session
        logger.info(f"Created agent execution session '{run_id}' for project '{project_id}'")
        return session

    def get_session(self, run_id: str) -> AgentExecutionSession:
        """Retrieve an active session or raise NotFoundException."""
        self.cleanup_expired_sessions()
        session = self._sessions.get(run_id)
        if not session:
            raise NotFoundException(message=f"Agent execution session '{run_id}' not found or expired")
        return session

    def update_session(self, run_id: str, status: str | None = None, context: dict[str, Any] | None = None) -> AgentExecutionSession:
        """Update session status or state context."""
        session = self.get_session(run_id)
        if status:
            session.status = status
        if context:
            session.context.update(context)
        session.updated_at = time.time()
        return session

    def cancel_session(self, run_id: str) -> AgentExecutionSession:
        """Mark session as cancelled."""
        return self.update_session(run_id, status="cancelled")

    def cleanup_expired_sessions(self) -> int:
        """Remove sessions exceeding TTL."""
        now = time.time()
        expired_keys = [
            sid for sid, s in self._sessions.items()
            if now - s.updated_at > self.session_ttl_seconds
        ]
        for sid in expired_keys:
            del self._sessions[sid]

        if expired_keys:
            logger.info(f"Cleaned up {len(expired_keys)} expired gateway execution sessions")
        return len(expired_keys)


_session_manager_instance: GatewaySessionManager | None = None


def get_session_manager() -> GatewaySessionManager:
    """Accessor for global GatewaySessionManager."""
    global _session_manager_instance
    if _session_manager_instance is None:
        _session_manager_instance = GatewaySessionManager()
    return _session_manager_instance
