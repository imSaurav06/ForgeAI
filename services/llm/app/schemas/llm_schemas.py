from typing import Any

from pydantic import BaseModel, Field



class GenerateRequest(BaseModel):
    """Request payload for single prompt text generation."""

    prompt: str = Field(..., description="User prompt text", json_schema_extra={"example": "Write a Python function for JWT validation."})
    mode: str = Field(default="CODE", description="Agent mode (ASK, PLAN, CODE, DEBUG, TEST, REVIEW, EXPLAIN)")
    context: str | None = Field(default=None, description="Optional RAG context snippet")
    model: str | None = Field(default=None, description="Model override")
    model_override: str | None = Field(default=None, description="Model override alias")
    temperature: float = Field(default=0.2, ge=0.0, le=1.0, description="Generation temperature")

    @property
    def effective_model(self) -> str | None:
        return self.model_override or self.model


class GenerateResponse(BaseModel):
    """Response payload for text generation."""

    model: str = Field(..., description="LLM model used")
    response: str = Field(..., description="Generated text completion or JSON string")
    structured_data: dict[str, Any] | None = Field(default=None, description="Parsed structured JSON output")


class ChatMessage(BaseModel):
    """Chat message node."""

    role: str = Field(..., description="Message role: system, user, assistant")
    content: str = Field(..., description="Message text content")


class ChatRequest(BaseModel):
    """Request payload for multi-turn chat generation."""

    messages: list[ChatMessage] = Field(..., description="Conversation messages history")
    model: str | None = Field(default=None, description="Model override")
    temperature: float = Field(default=0.2, description="Sampling temperature")


class ChatResponse(BaseModel):
    """Response payload for multi-turn chat generation."""

    model: str = Field(..., description="LLM model used")
    message: ChatMessage = Field(..., description="Assistant response message")


class StreamRequest(BaseModel):
    """Request payload for token streaming generation."""

    prompt: str = Field(..., description="User prompt text")
    mode: str = Field(default="CODE", description="Agent mode")
    context: str | None = Field(default=None, description="RAG context snippet")
    model: str | None = Field(default=None, description="Model override")


class LLMModelInfo(BaseModel):
    """Installed model metadata item."""

    id: str = Field(..., description="Model ID", json_schema_extra={"example": "qwen2.5-coder:7b-instruct-q4_0"})
    name: str = Field(..., description="Human readable model name")
    size_bytes: int | None = Field(default=None, description="Model size in bytes")
    is_active: bool = Field(default=False, description="Currently selected model flag")


class ModelSelectRequest(BaseModel):
    """Payload to select active model."""

    model_id: str = Field(..., description="Model ID to activate", json_schema_extra={"example": "qwen2.5-coder:7b-instruct-q4_0"})


class ModelSelectResponse(BaseModel):
    """Response confirming active model selection."""

    active_model: str = Field(..., description="Active model ID")
    status: str = Field(default="ready", description="Status")


class ModelHealthResponse(BaseModel):
    """Health check status response."""

    status: str = Field(..., description="Status (online/offline)")
    ollama_connected: bool = Field(..., description="Ollama API connectivity flag")
    active_model: str = Field(..., description="Currently active model ID")
    loaded_models: list[str] = Field(default_factory=list, description="Loaded models list")
