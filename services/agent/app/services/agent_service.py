import uuid
from typing import Any

from services.agent.app.core.events.event_bus import AgentEvent, get_agent_event_bus
from services.agent.app.core.sessions.session_store import AgentExecutionRun, get_agent_session_store
from services.agent.app.core.state_machine.states import AgentState
from services.agent.app.core.workflows.orchestrator import AgentWorkflowOrchestrator


class AgentService:
    """Service wrapper for Agent Orchestration, managing run lifecycles and workflow execution."""

    def __init__(self) -> None:
        self.session_store = get_agent_session_store()
        self.event_bus = get_agent_event_bus()
        self.orchestrator = AgentWorkflowOrchestrator()

    async def create_and_start_run(
        self,
        project_id: str,
        repository_id: str,
        mode: str,
        instruction: str,
        model: str = "qwen2.5-coder:7b-instruct-q4_0",
    ) -> AgentExecutionRun:
        """Create a new agent execution run and trigger workflow execution."""
        run_id = f"run_{uuid.uuid4().hex[:10]}"
        run = self.session_store.create_run(
            run_id=run_id,
            project_id=project_id,
            repository_id=repository_id,
            mode=mode,
            instruction=instruction,
            model=model,
        )

        # Trigger execution in workflow orchestrator asynchronously
        import asyncio
        asyncio.create_task(self.orchestrator.execute_run(run_id))
        
        # Return current state (which is initializing or planning)
        return self.session_store.get_run(run_id)

    def get_run(self, run_id: str) -> AgentExecutionRun:
        """Retrieve run state details by ID."""
        return self.session_store.get_run(run_id)

    async def continue_run(self, run_id: str, user_feedback: str | None = None) -> AgentExecutionRun:
        """Continue a run after user feedback or plan review."""
        run = self.session_store.get_run(run_id)
        if user_feedback:
            run.instruction += f"\nUser Feedback: {user_feedback}"
        
        import asyncio
        asyncio.create_task(self.orchestrator.execute_run(run_id))
        return self.session_store.get_run(run_id)

    def cancel_run(self, run_id: str) -> AgentExecutionRun:
        """Cancel an ongoing run."""
        run = self.session_store.get_run(run_id)
        run.state = AgentState.CANCELLED
        self.session_store.update_run(run)
        self.event_bus.emit(run_id, "agent.cancelled", {"status": "cancelled"})
        return run

    def get_run_steps(self, run_id: str) -> list[dict[str, Any]]:
        """Get executed steps history for a run."""
        run = self.session_store.get_run(run_id)
        return run.steps

    def get_run_events(self, run_id: str) -> list[AgentEvent]:
        """Get emitted event frames for a run."""
        return self.event_bus.get_events(run_id)
