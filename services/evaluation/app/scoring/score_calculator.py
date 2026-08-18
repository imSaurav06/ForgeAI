from pydantic import BaseModel

from services.evaluation.app.metrics.collector import PlatformMetricsSnapshot


class PlatformEvaluationScore(BaseModel):
    """Evaluation score breakdown model."""

    accuracy: float = 0.0
    reliability: float = 0.0
    success_rate: float = 0.0
    avg_latency_sec: float = 0.0
    avg_token_usage: int = 0
    recovery_success_rate: float = 0.0
    tool_reliability: float = 0.0
    overall_score: float = 0.0


class ScoreCalculator:
    """
    Weighted Platform Scoring Engine computing multi-dimensional performance
    metrics and weighted platform scores on a 0-100 scale.
    """

    @classmethod
    def calculate_score(cls, snapshot: PlatformMetricsSnapshot) -> PlatformEvaluationScore:
        """Calculate weighted platform scores from metrics snapshot."""
        # 1. Success Rate Score
        success_rate = snapshot.agent.completion_rate * 100.0

        # 2. Tool Reliability Score
        total_tools = max(snapshot.tool.commands_executed + snapshot.tool.test_runs, 1)
        tool_reliability = max(0.0, (total_tools - snapshot.tool.failures) / total_tools) * 100.0

        # 3. Recovery Success Score (Self-correction effectiveness)
        recovery_success = 100.0 if (snapshot.agent.repair_iterations == 0 or snapshot.agent.completion_rate == 1.0) else 50.0

        # 4. Accuracy (Retrieval RRF relevance + symbol coverage)
        accuracy = min(100.0, snapshot.retrieval.context_relevance * 100.0)

        # 5. Reliability (Tool reliability + Git rollbacks)
        git_penalty = snapshot.git.rollback_count * 15.0
        reliability = max(0.0, tool_reliability - git_penalty)

        # Latency & Token Usage
        latency = snapshot.llm.latency_sec + snapshot.agent.execution_time_sec
        tokens = snapshot.llm.total_tokens

        # Weighted Overall Score Calculation
        # Weights: Success Rate (35%), Accuracy (25%), Reliability (20%), Recovery (10%), Tool (10%)
        overall = (
            (success_rate * 0.35)
            + (accuracy * 0.25)
            + (reliability * 0.20)
            + (recovery_success * 0.10)
            + (tool_reliability * 0.10)
        )

        return PlatformEvaluationScore(
            accuracy=round(accuracy, 2),
            reliability=round(reliability, 2),
            success_rate=round(success_rate, 2),
            avg_latency_sec=round(latency, 3),
            avg_token_usage=tokens,
            recovery_success_rate=round(recovery_success, 2),
            tool_reliability=round(tool_reliability, 2),
            overall_score=round(overall, 2),
        )
