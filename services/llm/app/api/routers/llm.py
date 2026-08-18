import json

from fastapi import APIRouter, status
from fastapi.responses import StreamingResponse

from services.llm.app.schemas.llm_schemas import (
    ChatRequest,
    ChatResponse,
    GenerateRequest,
    GenerateResponse,
    LLMModelInfo,
    ModelHealthResponse,
    ModelSelectRequest,
    ModelSelectResponse,
    StreamRequest,
)
from services.llm.app.services.llm_service import LLMService
from shared.schemas.responses import ErrorResponse, SuccessResponse

router = APIRouter(tags=["LLM Inference"])
llm_service = LLMService()


@router.post(
    "/v1/generate",
    response_model=SuccessResponse[GenerateResponse],
    status_code=status.HTTP_200_OK,
    summary="Generate LLM Completion",
    description="Compiles prompt template for requested mode and generates text completion or structured JSON.",
    responses={
        200: {"model": SuccessResponse[GenerateResponse], "description": "Generation completed"},
        400: {"model": ErrorResponse, "description": "Invalid prompt or settings"},
    },
)
async def generate(payload: GenerateRequest) -> SuccessResponse[GenerateResponse]:
    res = await llm_service.generate(
        prompt=payload.prompt,
        mode=payload.mode,
        context=payload.context,
        model_override=payload.effective_model,
        temperature=payload.temperature,
    )
    return SuccessResponse(data=res, message="LLM generation completed")


@router.post(
    "/v1/chat",
    response_model=SuccessResponse[ChatResponse],
    summary="Chat Completion",
    description="Multi-turn conversation chat completion endpoint.",
    responses={
        200: {"model": SuccessResponse[ChatResponse], "description": "Chat completion response"},
    },
)
async def chat(payload: ChatRequest) -> SuccessResponse[ChatResponse]:
    res = await llm_service.chat(messages=payload.messages, model_override=payload.model)
    return SuccessResponse(data=res, message="Chat response generated")


@router.post(
    "/v1/stream",
    summary="Stream Token Completion (SSE)",
    description="Streams real-time LLM token chunks via Server-Sent Events.",
    responses={
        200: {"description": "Text/event-stream token stream"},
    },
)
async def generate_stream(payload: StreamRequest) -> StreamingResponse:
    async def token_generator():
        async for token in llm_service.generate_stream(
            prompt=payload.prompt,
            mode=payload.mode,
            context=payload.context,
            model_override=payload.model,
        ):
            chunk = {"token": token}
            yield f"data: {json.dumps(chunk)}\n\n"

    return StreamingResponse(token_generator(), media_type="text/event-stream")


@router.get(
    "/v1/models",
    response_model=SuccessResponse[list[LLMModelInfo]],
    summary="List Installed LLM Models",
    description="Returns available local Ollama coding models.",
    responses={
        200: {"model": SuccessResponse[list[LLMModelInfo]], "description": "Models list retrieved"},
    },
)
async def list_models() -> SuccessResponse[list[LLMModelInfo]]:
    models = await llm_service.list_models()
    return SuccessResponse(data=models, message="LLM models retrieved")


@router.post(
    "/v1/models/select",
    response_model=SuccessResponse[ModelSelectResponse],
    summary="Select Active LLM Model",
    description="Sets the primary active model for subsequent LLM tasks (e.g. QUALITY 7B vs FAST 3B).",
    responses={
        200: {"model": SuccessResponse[ModelSelectResponse], "description": "Active model updated"},
    },
)
async def select_model(payload: ModelSelectRequest) -> SuccessResponse[ModelSelectResponse]:
    resp = llm_service.select_model(payload.model_id)
    return SuccessResponse(data=resp, message="Active model selected")


@router.get(
    "/v1/models/health",
    response_model=SuccessResponse[ModelHealthResponse],
    summary="Get LLM Service Health",
    description="Checks Ollama connectivity and loaded models status.",
    responses={
        200: {"model": SuccessResponse[ModelHealthResponse], "description": "Health status retrieved"},
    },
)
async def get_models_health() -> SuccessResponse[ModelHealthResponse]:
    health = await llm_service.get_health()
    return SuccessResponse(data=health, message="LLM service health checked")
