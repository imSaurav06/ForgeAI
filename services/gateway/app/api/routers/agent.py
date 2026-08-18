import json
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import StreamingResponse

from services.gateway.app.api.dependencies.auth import verify_auth_token
from services.gateway.app.api.dependencies.proxy import get_proxy_service
from services.gateway.app.schemas.agent import (
    AgentMode,
    AgentRunActionRequest,
    AgentRunCreateRequest,
    AgentRunResponse,
    AgentStepResponse,
)
from services.gateway.app.services.proxy_service import GatewayProxyService
from shared.schemas.responses import ErrorResponse, SuccessResponse

router = APIRouter(prefix="/agent", tags=["Agent"])


@router.post(
    "/runs",
    response_model=SuccessResponse[AgentRunResponse],
    status_code=status.HTTP_202_ACCEPTED,
    summary="Create Agent Run Task",
    description="Initiates an asynchronous agent task workflow (ASK, PLAN, CODE, DEBUG, TEST, REVIEW, EXPLAIN).",
    responses={
        202: {"model": SuccessResponse[AgentRunResponse], "description": "Agent run created and started"},
        400: {"model": ErrorResponse, "description": "Invalid mode or request instructions"},
    },
)
async def create_agent_run(
    payload: AgentRunCreateRequest,
    request: Request,
    auth: dict = Depends(verify_auth_token),
    proxy: GatewayProxyService = Depends(get_proxy_service),
) -> Response:
    return await proxy.proxy_to_service("agent", "/v1/agent/runs", request, json_body=payload.model_dump())


@router.get(
    "/runs/{run_id}",
    response_model=SuccessResponse[AgentRunResponse],
    summary="Get Agent Run Status",
    description="Retrieves active execution status and step history of an agent run.",
    responses={
        200: {"model": SuccessResponse[AgentRunResponse], "description": "Run status retrieved"},
        404: {"model": ErrorResponse, "description": "Run ID not found"},
    },
)
async def get_agent_run(
    run_id: str,
    request: Request,
    auth: dict = Depends(verify_auth_token),
    proxy: GatewayProxyService = Depends(get_proxy_service),
) -> Response:
    return await proxy.proxy_to_service("agent", f"/v1/agent/runs/{run_id}", request)


@router.post(
    "/runs/{run_id}/continue",
    response_model=SuccessResponse[AgentRunResponse],
    summary="Continue Agent Run",
    description="Resumes a paused agent run after human review or approval.",
    responses={
        200: {"model": SuccessResponse[AgentRunResponse], "description": "Agent run resumed"},
        404: {"model": ErrorResponse, "description": "Run ID not found"},
    },
)
async def continue_agent_run(
    run_id: str,
    payload: AgentRunActionRequest,
    request: Request,
    auth: dict = Depends(verify_auth_token),
    proxy: GatewayProxyService = Depends(get_proxy_service),
) -> Response:
    return await proxy.proxy_to_service("agent", f"/v1/agent/runs/{run_id}/continue", request, json_body=payload.model_dump())


@router.post(
    "/runs/{run_id}/cancel",
    response_model=SuccessResponse[AgentRunResponse],
    summary="Cancel Agent Run",
    description="Cancels an active agent run task execution.",
    responses={
        200: {"model": SuccessResponse[AgentRunResponse], "description": "Agent run cancelled"},
        404: {"model": ErrorResponse, "description": "Run ID not found"},
    },
)
async def cancel_agent_run(
    run_id: str,
    request: Request,
    auth: dict = Depends(verify_auth_token),
    proxy: GatewayProxyService = Depends(get_proxy_service),
) -> Response:
    return await proxy.proxy_to_service("agent", f"/v1/agent/runs/{run_id}/cancel", request)


@router.get(
    "/runs/{run_id}/steps",
    response_model=SuccessResponse[list[AgentStepResponse]],
    summary="Get Agent Run Steps",
    description="Returns detailed breakdown of all tool, planning, and execution steps for a run.",
    responses={
        200: {"model": SuccessResponse[list[AgentStepResponse]], "description": "Steps retrieved"},
        404: {"model": ErrorResponse, "description": "Run ID not found"},
    },
)
async def get_agent_run_steps(
    run_id: str,
    request: Request,
    auth: dict = Depends(verify_auth_token),
    proxy: GatewayProxyService = Depends(get_proxy_service),
) -> Response:
    return await proxy.proxy_to_service("agent", f"/v1/agent/runs/{run_id}/steps", request)


@router.get(
    "/runs/{run_id}/stream",
    summary="Stream Agent Run Events (SSE)",
    description="Server-Sent Events (SSE) endpoint streaming real-time agent events (agent.started, plan.created, tool.started, test.passed, etc.).",
    responses={
        200: {"description": "Text/event-stream event stream"},
        404: {"model": ErrorResponse, "description": "Run ID not found"},
    },
)
async def stream_agent_run_events(
    run_id: str,
    request: Request,
    auth: dict = Depends(verify_auth_token),
) -> StreamingResponse:
    """SSE Stream proxy to agent microservice."""
    import httpx
    from services.gateway.app.core.internal_auth import InternalAuthManager
    from services.gateway.app.core.service_registry import get_service_registry

    async def event_generator() -> AsyncGenerator[str, None]:
        registry = get_service_registry()
        target_base = registry.get_service_url("agent")
        url = f"{target_base.rstrip('/')}/v1/agent/runs/{run_id}/stream"

        headers = {"Accept": "text/event-stream"}
        InternalAuthManager().inject_internal_headers(headers, user_id=auth.get("user_id"), user_role=auth.get("role"))
        
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("GET", url, headers=headers) as response:
                async for chunk in response.aiter_raw():
                    yield chunk.decode("utf-8", errors="replace")

    return StreamingResponse(event_generator(), media_type="text/event-stream")
