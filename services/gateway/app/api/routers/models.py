from fastapi import APIRouter, Depends, Request, Response

from services.gateway.app.api.dependencies.auth import verify_auth_token
from services.gateway.app.api.dependencies.proxy import get_proxy_service
from services.gateway.app.schemas.models import (
    BenchmarkMetric,
    LLMModelInfo,
    ModelBenchmarkReport,
    ModelHealthResponse,
    ModelSelectRequest,
    ModelSelectResponse,
)
from services.gateway.app.services.proxy_service import GatewayProxyService
from shared.schemas.responses import ErrorResponse, SuccessResponse

router = APIRouter(prefix="/models", tags=["Models"])


@router.get(
    "",
    response_model=SuccessResponse[list[LLMModelInfo]],
    summary="List Available LLM Models",
    description="Returns available Ollama coding models installed on the system.",
    responses={
        200: {"model": SuccessResponse[list[LLMModelInfo]], "description": "Models list retrieved"},
        503: {"model": ErrorResponse, "description": "LLM Service unavailable"},
    },
)
async def list_models(
    request: Request,
    auth: dict = Depends(verify_auth_token),
    proxy: GatewayProxyService = Depends(get_proxy_service),
) -> Response:
    return await proxy.proxy_to_service("llm", "/v1/models", request)


@router.post(
    "/select",
    response_model=SuccessResponse[ModelSelectResponse],
    summary="Select Active Model",
    description="Switches active LLM coding model (e.g., FAST 3B vs QUALITY 7B).",
    responses={
        200: {"model": SuccessResponse[ModelSelectResponse], "description": "Active model updated"},
        400: {"model": ErrorResponse, "description": "Model ID not installed or invalid"},
    },
)
async def select_model(
    payload: ModelSelectRequest,
    request: Request,
    auth: dict = Depends(verify_auth_token),
    proxy: GatewayProxyService = Depends(get_proxy_service),
) -> Response:
    return await proxy.proxy_to_service("llm", "/v1/models/select", request, json_body=payload.model_dump())


@router.get(
    "/health",
    response_model=SuccessResponse[ModelHealthResponse],
    summary="Get LLM Service & Ollama Connectivity Status",
    description="Checks connection status to Ollama host and currently loaded models.",
    responses={
        200: {"model": SuccessResponse[ModelHealthResponse], "description": "LLM health checked"},
    },
)
async def get_model_health(
    request: Request,
    auth: dict = Depends(verify_auth_token),
    proxy: GatewayProxyService = Depends(get_proxy_service),
) -> Response:
    return await proxy.proxy_to_service("llm", "/v1/models/health", request)


@router.get(
    "/benchmark",
    response_model=SuccessResponse[ModelBenchmarkReport],
    summary="Get Local Model Benchmark Report",
    description="Returns latency, throughput, RAM, VRAM, and JSON reliability benchmarks for evaluated local coding models.",
    responses={
        200: {"model": SuccessResponse[ModelBenchmarkReport], "description": "Benchmark report retrieved"},
    },
)
async def get_model_benchmark(
    request: Request,
    auth: dict = Depends(verify_auth_token),
    proxy: GatewayProxyService = Depends(get_proxy_service),
) -> Response:
    return await proxy.proxy_to_service("evaluation", "/v1/evaluations/benchmark", request)
