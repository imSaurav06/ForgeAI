import pytest
from fastapi.testclient import TestClient

from services.evaluation.app.benchmarks.benchmark_runner import BenchmarkRunner
from services.evaluation.app.history.history_store import EvaluationRecord, get_evaluation_history_store
from services.evaluation.app.main import app
from services.evaluation.app.metrics.collector import MetricsCollector
from services.evaluation.app.reports.report_generator import ReportGenerator
from services.evaluation.app.scoring.score_calculator import ScoreCalculator

client = TestClient(app)


def test_metrics_collector():
    """Verify operational telemetry collection."""
    snapshot = MetricsCollector.collect_from_run_data("run_eval_1", {"state": "COMPLETED", "repair_count": 0})
    assert snapshot.run_id == "run_eval_1"
    assert snapshot.agent.completion_rate == 1.0
    assert snapshot.llm.total_tokens > 0


def test_score_calculator():
    """Verify weighted platform score calculation."""
    snapshot = MetricsCollector.collect_from_run_data("run_eval_2", {"state": "COMPLETED", "repair_count": 1})
    scores = ScoreCalculator.calculate_score(snapshot)

    assert 0.0 <= scores.overall_score <= 100.0
    assert scores.success_rate == 100.0
    assert scores.avg_token_usage > 0


def test_benchmark_runner():
    """Verify benchmark runner execution across 7 modes."""
    res = BenchmarkRunner.run_benchmark_suite(target_model="qwen2.5-coder:7b-instruct-q4_0")

    assert res["total_suites_count"] == 7
    assert res["overall_benchmark_score"] >= 0.0
    modes_tested = [r["mode"] for r in res["task_results"]]
    for expected_mode in ["ASK", "PLAN", "CODE", "DEBUG", "TEST", "REVIEW", "EXPLAIN"]:
        assert expected_mode in modes_tested


def test_report_generator():
    """Verify Markdown report generation."""
    snapshot = MetricsCollector.collect_from_run_data("run_eval_3", {"state": "COMPLETED"})
    scores = ScoreCalculator.calculate_score(snapshot)
    md = ReportGenerator.generate_markdown_report("eval_123", snapshot, scores)

    assert "# Platform Evaluation Report" in md
    assert "Overall Score" in md


def test_history_store():
    """Verify evaluation history store and model comparisons."""
    store = get_evaluation_history_store()
    snapshot = MetricsCollector.collect_from_run_data("run_hist_1", {"selected_model": "qwen2.5-coder:7b-instruct-q4_0"})
    scores = ScoreCalculator.calculate_score(snapshot)

    rec = EvaluationRecord(
        evaluation_id="eval_hist_1",
        run_id="run_hist_1",
        model="qwen2.5-coder:7b-instruct-q4_0",
        repository="repo_1",
        scores=scores,
        metrics=snapshot,
        report_markdown="# Report",
    )
    store.save_record(rec)

    assert store.get_record("eval_hist_1").evaluation_id == "eval_hist_1"
    comparisons = store.get_model_comparisons()
    assert "qwen2.5-coder:7b-instruct-q4_0" in comparisons


@pytest.mark.asyncio
async def test_evaluation_api_endpoints():
    """Verify Evaluation Service API endpoints."""
    from services.gateway.app.core.internal_auth import InternalAuthManager
    headers = {"X-Internal-Service-Token": InternalAuthManager().generate_internal_token("test-client")}

    # Run Evaluation
    run_resp = client.post(
        "/v1/evaluations/run",
        headers=headers,
        json={
            "run_id": "run_eval_10",
            "model": "qwen2.5-coder:7b-instruct-q4_0",
            "repository": "repo_eval_10",
        },
    )
    assert run_resp.status_code == 201
    eval_id = run_resp.json()["data"]["evaluation_id"]

    # Benchmark Suite
    bm_resp = client.post("/v1/evaluations/benchmark", headers=headers, json={"model": "qwen2.5-coder:7b-instruct-q4_0"})
    assert bm_resp.status_code == 200
    assert bm_resp.json()["data"]["total_suites_count"] == 7

    # Get Details
    get_resp = client.get(f"/v1/evaluations/{eval_id}", headers=headers)
    assert get_resp.status_code == 200

    # Get History
    hist_resp = client.get("/v1/evaluations/history", headers=headers)
    assert hist_resp.status_code == 200
    assert len(hist_resp.json()["data"]) >= 1

    # Get Model Comparisons
    mod_resp = client.get("/v1/evaluations/models", headers=headers)
    assert mod_resp.status_code == 200

    # Get Reports
    rep_resp = client.get("/v1/evaluations/reports", headers=headers)
    assert rep_resp.status_code == 200
    assert len(rep_resp.json()["data"]) >= 1
