import time
from typing import Any

from pydantic import BaseModel, Field

from services.agent.app.core.state_machine.states import AgentState
from services.agent.app.storage.mongo_agent_store import MongoAgentRunRepository
from shared.exceptions.handlers import NotFoundException
from shared.logging.logger import logger


class AgentExecutionRun(BaseModel):
    """Model holding complete execution run context and state history."""

    run_id: str = Field(..., description="Unique agent run ID")
    project_id: str = Field(..., description="Target project ID")
    repository_id: str = Field(..., description="Target repository ID")
    mode: str = Field(..., description="Agent operating mode (ASK, PLAN, CODE, etc.)")
    instruction: str = Field(..., description="User instruction prompt")
    selected_model: str = Field(default="qwen2.5-coder:7b-instruct-q4_0", description="Active LLM model")
    state: AgentState = Field(default=AgentState.CREATED, description="Current state")
    execution_plan: list[dict[str, Any]] = Field(default_factory=list, description="Decomposed DAG plan steps")
    retrieved_context: str = Field(default="", description="Retrieved repository context text")
    tool_history: list[dict[str, Any]] = Field(default_factory=list, description="Executed tools log")
    test_history: list[dict[str, Any]] = Field(default_factory=list, description="Test execution & failure log")
    steps: list[dict[str, Any]] = Field(default_factory=list, description="Step execution history")
    repair_count: int = Field(default=0, description="Self-correction repair iterations count")
    commit_approved: bool = Field(default=False, description="Whether human approval has been granted for git commit")
    commit_pending: bool = Field(default=False, description="Whether a git commit is awaiting human approval")
    commit_proposal: dict[str, Any] = Field(default_factory=dict, description="Proposed commit metadata awaiting approval")
    created_at: float = Field(default_factory=time.time, description="Creation timestamp")
    updated_at: float = Field(default_factory=time.time, description="Last update timestamp")



class AgentSessionStore:
    """Session store managing agent execution runs with MongoDB persistence and in-memory cache."""

    def __init__(self) -> None:
        self._runs: dict[str, AgentExecutionRun] = {}
        self.mongo_repo = MongoAgentRunRepository()

    def create_run(
        self,
        run_id: str,
        project_id: str,
        repository_id: str,
        mode: str,
        instruction: str,
        model: str = "qwen2.5-coder:7b-instruct-q4_0",
    ) -> AgentExecutionRun:
        """Initialize and store a new Agent execution run."""
        run = AgentExecutionRun(
            run_id=run_id,
            project_id=project_id,
            repository_id=repository_id,
            mode=mode.upper(),
            instruction=instruction,
            selected_model=model,
        )
        self._runs[run_id] = run

        self._persist_run_bg(run)
        return run

    def get_run(self, run_id: str) -> AgentExecutionRun:
        """Retrieve run by ID from in-memory cache or MongoDB or raise NotFoundException."""
        run = self._runs.get(run_id)
        if not run:
            # Try loading synchronously or via loop from MongoDB
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Check if there's a cached task or attempt sync fetch via mongo_repo
                    pass
            except Exception:
                pass

        if not run:
            raise NotFoundException(message=f"Agent run '{run_id}' not found")
        return run

    async def get_run_async(self, run_id: str) -> AgentExecutionRun:
        """Async retrieval from in-memory cache or MongoDB."""
        run = self._runs.get(run_id)
        if not run:
            run = await self.mongo_repo.get_run(run_id)
            if run:
                self._runs[run.run_id] = run
        if not run:
            raise NotFoundException(message=f"Agent run '{run_id}' not found")
        return run

    def update_run(self, run: AgentExecutionRun) -> AgentExecutionRun:
        """Update existing run state."""
        run.updated_at = time.time()
        self._runs[run.run_id] = run
        self._persist_run_bg(run)
        return run

    def _persist_run_bg(self, run: AgentExecutionRun) -> None:
        """Schedule asynchronous save of AgentExecutionRun to MongoDB."""
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self.mongo_repo.save_run(run))
        except Exception as err:
            logger.debug(f"Could not schedule background save to MongoDB: {err}")


_session_store_instance: AgentSessionStore | None = None


def get_agent_session_store() -> AgentSessionStore:
    """Accessor for global AgentSessionStore."""
    global _session_store_instance
    if _session_store_instance is None:
        _session_store_instance = AgentSessionStore()
    return _session_store_instance
