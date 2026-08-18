from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class AgentMode(str, Enum):
    ASK = "ASK"
    PLAN = "PLAN"
    CODE = "CODE"
    DEBUG = "DEBUG"
    TEST = "TEST"
    REVIEW = "REVIEW"
    EXPLAIN = "EXPLAIN"


class AgentRunCreateRequest(BaseModel):
    """Request payload to launch an agent task execution."""

    project_id: str = Field(default="proj_default", description="Target project workspace ID")
    repository_id: str = Field(default="repo_default", description="Target repository ID")
    mode: AgentMode = Field(default=AgentMode.CODE, description="Operating mode for the agent task")
    instruction: str = Field(..., description="User coding task instruction or query", json_schema_extra={"example": "Add /health endpoint"})
    model_name: str | None = Field(default=None, description="Optional LLM model override")


class AgentStepResponse(BaseModel):
    """Agent execution step node detail."""

    step_id: str = Field(..., description="Unique step ID")
    run_id: str = Field(..., description="Parent run ID")
    type: str = Field(..., description="Step type: plan, tool_call, llm_reasoning, patch, test")
    title: str = Field(..., description="Step human readable summary")
    status: str = Field(..., description="Step status: pending, running, completed, failed")
    details: dict[str, Any] = Field(default_factory=dict, description="Step payload & artifacts")


class AgentRunResponse(BaseModel):
    """Agent task execution state response."""

    run_id: str = Field(..., description="Unique agent run execution ID")
    project_id: str = Field(..., description="Target project ID")
    mode: AgentMode = Field(..., description="Selected agent mode")
    instruction: str = Field(..., description="User instruction")
    status: str = Field(default="started", description="Run status: started, planning, executing, repairing, completed, failed, cancelled")
    current_step: str | None = Field(default=None, description="Active step name")
    plan: list[str] = Field(default_factory=list, description="Generated task execution plan steps")
    steps: list[AgentStepResponse] = Field(default_factory=list, description="Execution steps history")


class AgentRunActionRequest(BaseModel):
    """Payload for user interaction actions on active agent run."""

    user_feedback: str | None = Field(default=None, description="Optional approval or correction instruction")
