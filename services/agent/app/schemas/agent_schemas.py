from typing import Any

from pydantic import BaseModel, Field

from services.agent.app.core.state_machine.states import AgentState


class AgentRunCreateRequest(BaseModel):
    """Request payload to initiate a new autonomous agent run."""

    project_id: str = Field(default="proj_default", description="Target project ID", json_schema_extra={"example": "proj_12345"})
    repository_id: str = Field(..., description="Target repository ID", json_schema_extra={"example": "repo_auth_svc"})
    mode: str = Field(default="CODE", description="Agent mode (ASK, PLAN, CODE, DEBUG, TEST, REVIEW, EXPLAIN)")
    instruction: str = Field(..., description="Task instruction prompt", json_schema_extra={"example": "Implement JWT authentication middleware"})
    model: str | None = Field(default=None, description="Selected LLM model")
    model_name: str | None = Field(default=None, description="Selected LLM model alias")

    @property
    def selected_model(self) -> str:
        return self.model_name or self.model or "qwen2.5-coder:3b-instruct-q4_0"


class AgentRunContinueRequest(BaseModel):
    """Request payload to continue a paused or plan-awaiting agent run."""

    user_feedback: str | None = Field(default=None, description="User plan feedback or confirmation")


class AgentRunStatusResponse(BaseModel):
    """Status response model for an agent execution run."""

    run_id: str = Field(..., description="Run ID")
    project_id: str = Field(..., description="Project ID")
    repository_id: str = Field(..., description="Repository ID")
    mode: str = Field(..., description="Mode")
    instruction: str = Field(..., description="Instruction")
    state: AgentState = Field(..., description="Current state machine state")
    repair_count: int = Field(..., description="Count of self-correction repair loops executed")
    execution_plan: dict[str, Any] | list[dict[str, Any]] = Field(default_factory=list, description="Decomposed plan steps")
    steps: list[dict[str, Any]] = Field(default_factory=list, description="Execution steps history")
    created_at: float = Field(..., description="Creation epoch timestamp")
    updated_at: float = Field(..., description="Last update epoch timestamp")


class AgentEventItem(BaseModel):
    """Agent event frame item model."""

    run_id: str = Field(..., description="Run ID")
    event_type: str = Field(..., description="Event type name")
    payload: dict[str, Any] = Field(default_factory=dict, description="Event data payload")
    timestamp: float = Field(..., description="Emission timestamp")
