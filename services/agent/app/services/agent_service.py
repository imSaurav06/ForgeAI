import uuid
from typing import Any

from services.agent.app.core.events.event_bus import AgentEvent, get_agent_event_bus
from services.agent.app.core.sessions.session_store import AgentExecutionRun, get_agent_session_store
from services.agent.app.core.state_machine.states import AgentState
from services.agent.app.core.workflows.orchestrator import AgentWorkflowOrchestrator


from services.agent.app.core.tools.tool_dispatcher import AgentToolDispatcher


class AgentService:
    """Service wrapper for Agent Orchestration, managing run lifecycles and workflow execution."""

    def __init__(self) -> None:
        self.session_store = get_agent_session_store()
        self.event_bus = get_agent_event_bus()
        self.orchestrator = AgentWorkflowOrchestrator()
        self.tool_dispatcher = AgentToolDispatcher()

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
        asyncio.create_task(self.orchestrator.execute_dynamic_tool_loop(run_id))

        # Return current state (which is initializing or planning)
        return self.session_store.get_run(run_id)

    def get_run(self, run_id: str) -> AgentExecutionRun:
        """Retrieve run state details by ID."""
        return self.session_store.get_run(run_id)

    async def continue_run(self, run_id: str, user_feedback: str | None = None) -> AgentExecutionRun:
        """Continue a run after user feedback, plan review, commit approval, or rejection."""
        run = self.session_store.get_run(run_id)
        feedback_upper = str(user_feedback or "").strip().upper()

        if getattr(run, "commit_pending", False):
            proposal = getattr(run, "commit_proposal", {}) or {}
            if any(w in feedback_upper for w in ("APPROVE", "APPROVED", "YES", "CONFIRM", "PROCEED")):
                run.commit_approved = True
                run.commit_pending = False
                
                # Execute the approved git commit
                commit_msg = proposal.get("message") or "Probe commit"
                commit_files = proposal.get("files")
                commit_repo = proposal.get("repository_id") or run.repository_id
                
                try:
                    commit_res = await self.tool_dispatcher.git_commit(
                        repository_id=commit_repo,
                        message=commit_msg,
                        files=commit_files,
                    )
                except Exception as commit_err:
                    commit_res = {"status": "failed", "error": str(commit_err)}

                run.steps.append({
                    "step": f"step_{len(run.steps)+1}_git_commit",
                    "thought": "User approved commit proposal. Executing Git commit.",
                    "arguments": {"repository_id": commit_repo, "message": commit_msg, "files": commit_files},
                    "output": commit_res,
                })
                run.state = AgentState.COMPLETED
                self.session_store.update_run(run)
                self.event_bus.emit(run_id, "git.approval.granted", {"run_id": run_id, "proposal": proposal})
                self.event_bus.emit(run_id, "git.commit.completed", {"result": commit_res})
                self.event_bus.emit(run_id, "agent.completed", {"status": "completed", "response": f"Commit executed successfully: {commit_res.get('commit_hash', '')}"})
                return run
            elif any(w in feedback_upper for w in ("REJECT", "REJECTED", "NO", "CANCEL", "DISMISS")):
                run.commit_approved = False
                run.commit_pending = False
                run.state = AgentState.COMPLETED
                run.steps.append({
                    "step": "step_commit_rejected",
                    "thought": "User rejected commit proposal",
                    "output": {"status": "rejected", "message": "Commit rejected by user. No Git commit was created."},
                })
                self.session_store.update_run(run)
                self.event_bus.emit(run_id, "git.approval.rejected", {"run_id": run_id, "proposal": proposal, "reason": user_feedback})
                self.event_bus.emit(run_id, "agent.completed", {"status": "completed", "response": "Commit rejected by user. Working tree preserved without commit."})
                return run


        if user_feedback:
            run.instruction += f"\nUser Feedback: {user_feedback}"

        import asyncio
        asyncio.create_task(self.orchestrator.execute_dynamic_tool_loop(run_id))
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
