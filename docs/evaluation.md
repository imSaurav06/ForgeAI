# ForgeAI — Evaluation, Benchmarking & Metrics Suite

## Overview
The **Evaluation Service** (`forge_evaluation`, port `8007`) provides continuous, reproducible performance benchmarking for coding LLMs and autonomous agent workflows across all 7 execution modes (`ASK`, `PLAN`, `CODE`, `DEBUG`, `TEST`, `REVIEW`, `EXPLAIN`).

---

## 1. Evaluation Dimensions & Scoring Formula

Every completed agent run is scored against 5 weighted quality dimensions:

| Dimension | Weight | Metric Description |
| :--- | :--- | :--- |
| **Code Accuracy** | `0.30` | Successful implementation of requested feature without syntax/runtime regressions. |
| **Syntax Validity** | `0.20` | Zero AST parse errors and clean linter / typecheck validation. |
| **AST Resolution** | `0.20` | Accuracy of symbol reference resolutions and dependency linkage. |
| **Rollback Rate** | `0.15` | Minimal patch reversals and self-correction iterations. |
| **Execution Latency** | `0.15` | Wall-clock execution time and token generation throughput. |

### Aggregate Score Formula:
$$Score_{total} = \sum_{i=1}^{5} w_i \times S_i \in [0.0, 1.0]$$

---

## 2. Repeatable Benchmark Suite

- **7-Mode Benchmark**: The benchmark engine executes standardized prompt fixtures across each mode.
- **Model Comparison**: Measures token throughput (tokens/sec), latency, memory footprint, and pass rates between `qwen2.5-coder:7b-instruct-q4_0` and `qwen2.5-coder:3b-instruct-q4_0`.
- **Markdown Report Generation**: Automatically compiles evaluation metrics into human-readable Markdown reports persisted in MongoDB and accessible via `GET /v1/evaluations/reports`.

---

## 3. API Endpoints Reference

- `POST /v1/evaluations/run`: Evaluate a specific agent execution run by `run_id`.
- `POST /v1/evaluations/benchmark`: Execute the full 7-mode benchmark suite.
- `GET /v1/evaluations/benchmark`: Retrieve latest benchmark report.
- `GET /v1/evaluations/history`: List historical evaluation results.
- `GET /v1/evaluations/models`: Compare aggregate metrics across different models.
