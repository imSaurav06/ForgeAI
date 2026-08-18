
from pydantic import BaseModel, Field


class LLMModelInfo(BaseModel):
    """Model information schema."""

    id: str = Field(..., description="Model identifier name", json_schema_extra={"example": "qwen2.5-coder:7b-instruct-q4_0"})
    name: str = Field(..., description="Human readable model name")
    size_bytes: int | None = Field(default=None, description="Model file size in bytes")
    parameter_size: str | None = Field(default=None, description="Parameter count e.g. 7B, 3B")
    quantization: str | None = Field(default=None, description="Quantization e.g. Q4_0, Q8_0")
    is_active: bool = Field(default=False, description="Currently selected model flag")


class ModelSelectRequest(BaseModel):
    """Request payload to select active LLM model."""

    model_id: str = Field(..., description="Model identifier to activate", json_schema_extra={"example": "qwen2.5-coder:7b-instruct-q4_0"})


class ModelSelectResponse(BaseModel):
    """Response confirming model selection."""

    active_model: str = Field(..., description="Newly selected active model ID")
    status: str = Field(default="ready", description="Model readiness status")


class ModelHealthResponse(BaseModel):
    """LLM provider service health status."""

    status: str = Field(..., description="Ollama / LLM status (online/offline)")
    ollama_connected: bool = Field(..., description="Flag indicating Ollama API connectivity")
    active_model: str | None = Field(default=None, description="Currently loaded model name")
    loaded_models: list[str] = Field(default_factory=list, description="Currently warm loaded models")


class BenchmarkMetric(BaseModel):
    """Benchmark performance entry for model comparison."""

    model: str = Field(..., description="Model name")
    ram_mb: float = Field(..., description="RAM consumption in MB")
    vram_mb: float = Field(..., description="VRAM consumption in MB")
    ttft_ms: float = Field(..., description="Time to first token in milliseconds")
    tokens_per_sec: float = Field(..., description="Generation throughput tokens/sec")
    tool_reliability_score: float = Field(..., description="Tool calling accuracy percentage")
    json_reliability_score: float = Field(..., description="Structured JSON compliance percentage")


class ModelBenchmarkReport(BaseModel):
    """Local benchmark execution report."""

    timestamp: str = Field(..., description="Benchmark timestamp")
    results: list[BenchmarkMetric] = Field(default_factory=list)
    recommended_quality_model: str = Field(..., description="Recommended quality coding model")
    recommended_fast_model: str = Field(..., description="Recommended fast classification model")
