from typing import Any

from pydantic import BaseModel, Field

from services.evaluation.app.metrics.collector import PlatformMetricsSnapshot
from services.evaluation.app.scoring.score_calculator import PlatformEvaluationScore


class EvaluationRunRequest(BaseModel):
    """Payload to trigger single agent run evaluation."""

    run_id: str = Field(..., description="Target agent run ID", json_schema_extra={"example": "run_12345"})
    repository_id: str = Field(default="repo_forge_ai", description="Target repository ID")


class BenchmarkRunRequest(BaseModel):
    """Payload to trigger benchmark suite execution."""

    model: str = Field(default="qwen2.5-coder:7b-instruct-q4_0", description="Target LLM model to benchmark")
    repository_id: str = Field(default="repo_forge_ai", description="Target repository ID")


class EvaluationRunResponse(BaseModel):
    """Evaluation result response model."""

    evaluation_id: str = Field(..., description="Unique evaluation ID")
    run_id: str = Field(..., description="Target run ID")
    scores: PlatformEvaluationScore = Field(..., description="Calculated scores breakdown")
    metrics: PlatformMetricsSnapshot = Field(..., description="Raw operational metrics snapshot")
    report_markdown: str = Field(..., description="Generated Markdown report")


class BenchmarkRunResponse(BaseModel):
    """Benchmark suite execution response model."""

    target_model: str = Field(..., description="Model tested")
    repository_id: str = Field(..., description="Repository ID")
    overall_benchmark_score: float = Field(..., description="Overall benchmark quality score (0-100)")
    passed_suites_count: int = Field(..., description="Passed benchmark tasks count")
    total_suites_count: int = Field(..., description="Total benchmark tasks count")
    task_results: list[dict[str, Any]] = Field(default_factory=list, description="Per-mode task results")
