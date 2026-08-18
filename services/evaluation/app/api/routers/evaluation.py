from typing import Any

from fastapi import APIRouter, status

from services.evaluation.app.schemas.evaluation_schemas import (
    BenchmarkRunRequest,
    BenchmarkRunResponse,
    EvaluationRunRequest,
    EvaluationRunResponse,
)
from services.evaluation.app.services.evaluation_service import EvaluationService
from shared.schemas.responses import ErrorResponse, SuccessResponse

router = APIRouter(prefix="/v1/evaluations", tags=["Evaluation & Benchmarks"])
eval_service = EvaluationService()


@router.post(
    "/run",
    response_model=SuccessResponse[EvaluationRunResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Evaluate Agent Execution Run",
    description="Measures metrics, calculates weighted scores, and generates Markdown performance report for a run.",
    responses={
        201: {"model": SuccessResponse[EvaluationRunResponse], "description": "Evaluation completed"},
        400: {"model": ErrorResponse, "description": "Invalid run request"},
    },
)
async def evaluate_run(payload: EvaluationRunRequest) -> SuccessResponse[EvaluationRunResponse]:
    record = await eval_service.evaluate_agent_run(run_id=payload.run_id, repository_id=payload.repository_id)
    resp = EvaluationRunResponse(
        evaluation_id=record.evaluation_id,
        run_id=record.run_id,
        scores=record.scores,
        metrics=record.metrics,
        report_markdown=record.report_markdown,
    )
    return SuccessResponse(data=resp, message="Evaluation completed successfully")


@router.post(
    "/benchmark",
    response_model=SuccessResponse[BenchmarkRunResponse],
    status_code=status.HTTP_200_OK,
    summary="Run Benchmark Suite Across 7 Modes",
    description="Executes repeatable benchmark suite for ASK, PLAN, CODE, DEBUG, TEST, REVIEW, EXPLAIN modes.",
    responses={
        200: {"model": SuccessResponse[BenchmarkRunResponse], "description": "Benchmark suite completed"},
    },
)
async def run_benchmark(payload: BenchmarkRunRequest) -> SuccessResponse[BenchmarkRunResponse]:
    result = eval_service.run_benchmark(model=payload.model, repository_id=payload.repository_id)
    resp = BenchmarkRunResponse(**result)
    return SuccessResponse(data=resp, message="Benchmark suite executed successfully")


@router.get(
    "/history",
    response_model=SuccessResponse[list[EvaluationRunResponse]],
    summary="Get Evaluation History",
    description="Returns list of historical evaluation records.",
    responses={
        200: {"model": SuccessResponse[list[EvaluationRunResponse]], "description": "Evaluation history retrieved"},
    },
)
async def get_history() -> SuccessResponse[list[EvaluationRunResponse]]:
    records = eval_service.get_history()
    items = [
        EvaluationRunResponse(
            evaluation_id=r.evaluation_id,
            run_id=r.run_id,
            scores=r.scores,
            metrics=r.metrics,
            report_markdown=r.report_markdown,
        )
        for r in records
    ]
    return SuccessResponse(data=items, message="Evaluation history retrieved")


@router.get(
    "/models",
    response_model=SuccessResponse[dict[str, Any]],
    summary="Get Model Comparisons",
    description="Compares performance metrics, scores, token usage, and latency grouped by LLM model.",
    responses={
        200: {"model": SuccessResponse[dict[str, Any]], "description": "Model comparisons retrieved"},
    },
)
async def get_models_comparison() -> SuccessResponse[dict[str, Any]]:
    comparisons = eval_service.get_model_comparisons()
    return SuccessResponse(data=comparisons, message="Model comparisons retrieved")


@router.get(
    "/reports",
    response_model=SuccessResponse[list[dict[str, Any]]],
    summary="Get Evaluation Markdown Reports",
    description="Retrieves generated Markdown evaluation reports.",
    responses={
        200: {"model": SuccessResponse[list[dict[str, Any]]], "description": "Reports retrieved"},
    },
)
async def get_reports() -> SuccessResponse[list[dict[str, Any]]]:
    records = eval_service.get_history()
    reports = [
        {
            "evaluation_id": r.evaluation_id,
            "run_id": r.run_id,
            "model": r.model,
            "overall_score": r.scores.overall_score,
            "report_markdown": r.report_markdown,
        }
        for r in records
    ]
    return SuccessResponse(data=reports, message="Evaluation markdown reports retrieved")


@router.get(
    "/{id}",
    response_model=SuccessResponse[EvaluationRunResponse],
    summary="Get Evaluation Details",
    description="Retrieves a specific evaluation record by ID.",
    responses={
        200: {"model": SuccessResponse[EvaluationRunResponse], "description": "Evaluation details retrieved"},
        404: {"model": ErrorResponse, "description": "Evaluation ID not found"},
    },
)
async def get_evaluation(id: str) -> SuccessResponse[EvaluationRunResponse]:
    record = eval_service.get_evaluation(id)
    resp = EvaluationRunResponse(
        evaluation_id=record.evaluation_id,
        run_id=record.run_id,
        scores=record.scores,
        metrics=record.metrics,
        report_markdown=record.report_markdown,
    )
    return SuccessResponse(data=resp, message="Evaluation details retrieved")
