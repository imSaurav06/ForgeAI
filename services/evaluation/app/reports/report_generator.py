from services.evaluation.app.metrics.collector import PlatformMetricsSnapshot
from services.evaluation.app.scoring.score_calculator import PlatformEvaluationScore


class ReportGenerator:
    """Report Generator producing structured JSON summaries and Markdown evaluation reports."""

    @classmethod
    def generate_markdown_report(
        cls,
        evaluation_id: str,
        snapshot: PlatformMetricsSnapshot,
        scores: PlatformEvaluationScore,
    ) -> str:
        """Generate formatted GitHub Markdown evaluation report."""
        md = f"""# Platform Evaluation Report - `{evaluation_id}`

## Overall Score: `{scores.overall_score} / 100`

### Performance Metrics Breakdown
| Metric | Value |
| :--- | :--- |
| **Success Rate** | `{scores.success_rate}%` |
| **Accuracy** | `{scores.accuracy}%` |
| **Reliability** | `{scores.reliability}%` |
| **Recovery Success Rate** | `{scores.recovery_success_rate}%` |
| **Tool Reliability** | `{scores.tool_reliability}%` |
| **Average Latency** | `{scores.avg_latency_sec} sec` |
| **Token Consumption** | `{scores.avg_token_usage} tokens` |

---

### Per-Service Telemetry Summary

#### 1. Agent Service
- **Completion Rate**: `{snapshot.agent.completion_rate * 100}%`
- **Self-Correction Repair Loops**: `{snapshot.agent.repair_iterations}`
- **Execution Time**: `{snapshot.agent.execution_time_sec}s`

#### 2. Retrieval / Code RAG Service
- **Context Relevance**: `{snapshot.retrieval.context_relevance * 100}%`
- **Retrieved Symbols**: `{snapshot.retrieval.retrieved_symbols}`
- **Context Size**: `{snapshot.retrieval.context_size_chars} chars`

#### 3. LLM Service
- **Model**: `{snapshot.llm.model_name}`
- **Total Tokens**: `{snapshot.llm.total_tokens}` (Prompt: `{snapshot.llm.prompt_tokens}`, Completion: `{snapshot.llm.completion_tokens}`)
- **Latency**: `{snapshot.llm.latency_sec}s`

#### 4. Tool Execution Service
- **Commands Executed**: `{snapshot.tool.commands_executed}`
- **Test Runs**: `{snapshot.tool.test_runs}`
- **Failures**: `{snapshot.tool.failures}`

#### 5. Git Service
- **Commits**: `{snapshot.git.commits}`
- **Patches Applied**: `{snapshot.git.patches}`
- **Rollbacks**: `{snapshot.git.rollback_count}`
"""
        return md.strip()
