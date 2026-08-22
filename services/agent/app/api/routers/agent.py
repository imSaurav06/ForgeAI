from typing import Any

from fastapi import APIRouter, status

from services.agent.app.schemas.agent_schemas import (
    AgentEventItem,
    AgentRunContinueRequest,
    AgentRunCreateRequest,
    AgentRunStatusResponse,
)
from services.agent.app.services.agent_service import AgentService
from shared.schemas.responses import ErrorResponse, SuccessResponse

router = APIRouter(prefix="/v1/agent", tags=["Agent Orchestration"])
agent_service = AgentService()


@router.post(
    "/runs",
    response_model=SuccessResponse[AgentRunStatusResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create & Start Agent Execution Run",
    description="Initiates an autonomous agent execution run across 11 state machine states with self-correction support.",
    responses={
        201: {"model": SuccessResponse[AgentRunStatusResponse], "description": "Agent run created and executed"},
        400: {"model": ErrorResponse, "description": "Invalid run request"},
    },
)
async def create_run(payload: AgentRunCreateRequest) -> SuccessResponse[AgentRunStatusResponse]:
    run = await agent_service.create_and_start_run(
        project_id=payload.project_id,
        repository_id=payload.repository_id,
        mode=payload.mode,
        instruction=payload.instruction,
        model=payload.selected_model,
    )
    status_resp = AgentRunStatusResponse(
        run_id=run.run_id,
        project_id=run.project_id,
        repository_id=run.repository_id,
        mode=run.mode,
        instruction=run.instruction,
        state=run.state,
        repair_count=run.repair_count,
        execution_plan=run.execution_plan,
        steps=run.steps,
        created_at=run.created_at,
        updated_at=run.updated_at,
    )
    return SuccessResponse(data=status_resp, message="Agent run executed")


@router.get(
    "/runs/{run_id}",
    response_model=SuccessResponse[AgentRunStatusResponse],
    summary="Get Agent Run Status",
    description="Retrieves current state machine state and execution details for a run ID.",
    responses={
        200: {"model": SuccessResponse[AgentRunStatusResponse], "description": "Run status retrieved"},
        404: {"model": ErrorResponse, "description": "Run ID not found"},
    },
)
async def get_run(run_id: str) -> SuccessResponse[AgentRunStatusResponse]:
    run = agent_service.get_run(run_id)
    status_resp = AgentRunStatusResponse(
        run_id=run.run_id,
        project_id=run.project_id,
        repository_id=run.repository_id,
        mode=run.mode,
        instruction=run.instruction,
        state=run.state,
        repair_count=run.repair_count,
        execution_plan=run.execution_plan,
        steps=run.steps,
        commit_approved=getattr(run, "commit_approved", False),
        commit_pending=getattr(run, "commit_pending", False),
        commit_proposal=getattr(run, "commit_proposal", {}) or {},
        created_at=run.created_at,
        updated_at=run.updated_at,
    )
    return SuccessResponse(data=status_resp, message="Agent run status retrieved")


@router.post(
    "/runs/{run_id}/continue",
    response_model=SuccessResponse[AgentRunStatusResponse],
    summary="Continue Agent Execution Run",
    description="Continues a paused agent run with user feedback or approval.",
    responses={
        200: {"model": SuccessResponse[AgentRunStatusResponse], "description": "Run continued"},
    },
)
async def continue_run(run_id: str, payload: AgentRunContinueRequest | None = None) -> SuccessResponse[AgentRunStatusResponse]:
    feedback = payload.user_feedback if payload else None
    run = await agent_service.continue_run(run_id, user_feedback=feedback)
    status_resp = AgentRunStatusResponse(
        run_id=run.run_id,
        project_id=run.project_id,
        repository_id=run.repository_id,
        mode=run.mode,
        instruction=run.instruction,
        state=run.state,
        repair_count=run.repair_count,
        execution_plan=run.execution_plan,
        steps=run.steps,
        commit_approved=getattr(run, "commit_approved", False),
        commit_pending=getattr(run, "commit_pending", False),
        commit_proposal=getattr(run, "commit_proposal", {}) or {},
        created_at=run.created_at,
        updated_at=run.updated_at,
    )
    return SuccessResponse(data=status_resp, message="Agent run continued")


@router.post(
    "/runs/{run_id}/cancel",
    response_model=SuccessResponse[AgentRunStatusResponse],
    summary="Cancel Agent Execution Run",
    description="Cancels an ongoing agent execution run.",
    responses={
        200: {"model": SuccessResponse[AgentRunStatusResponse], "description": "Run cancelled"},
    },
)
async def cancel_run(run_id: str) -> SuccessResponse[AgentRunStatusResponse]:
    run = agent_service.cancel_run(run_id)
    status_resp = AgentRunStatusResponse(
        run_id=run.run_id,
        project_id=run.project_id,
        repository_id=run.repository_id,
        mode=run.mode,
        instruction=run.instruction,
        state=run.state,
        repair_count=run.repair_count,
        execution_plan=run.execution_plan,
        steps=run.steps,
        commit_approved=getattr(run, "commit_approved", False),
        commit_pending=getattr(run, "commit_pending", False),
        commit_proposal=getattr(run, "commit_proposal", {}) or {},
        created_at=run.created_at,
        updated_at=run.updated_at,
    )
    return SuccessResponse(data=status_resp, message="Agent run cancelled")



@router.get(
    "/runs/{run_id}/steps",
    response_model=SuccessResponse[list[dict[str, Any]]],
    summary="Get Agent Run Execution Steps",
    description="Retrieves executed steps log for a run.",
    responses={
        200: {"model": SuccessResponse[list[dict[str, Any]]], "description": "Steps retrieved"},
    },
)
async def get_run_steps(run_id: str) -> SuccessResponse[list[dict[str, Any]]]:
    steps = agent_service.get_run_steps(run_id)
    return SuccessResponse(data=steps, message="Agent run steps retrieved")


@router.get(
    "/runs/{run_id}/events",
    response_model=SuccessResponse[list[AgentEventItem]],
    summary="Get Agent Emitted Event Frames",
    description="Returns real-time event stream frames emitted during agent run.",
    responses={
        200: {"model": SuccessResponse[list[AgentEventItem]], "description": "Events retrieved"},
    },
)
async def get_run_events(run_id: str) -> SuccessResponse[list[AgentEventItem]]:
    events = agent_service.get_run_events(run_id)
    items = [
        AgentEventItem(
            run_id=e.run_id,
            event_type=e.event_type,
            payload=e.payload,
            timestamp=e.timestamp,
        )
        for e in events
    ]
    return SuccessResponse(data=items, message="Agent run events retrieved")


from fastapi.responses import StreamingResponse
import json

@router.get(
    "/runs/{run_id}/stream",
    summary="Stream Agent Run Events (SSE)",
    description="Server-Sent Events (SSE) endpoint streaming real-time agent events.",
    responses={
        200: {"description": "Text/event-stream event stream"},
        404: {"model": ErrorResponse, "description": "Run ID not found"},
    },
)
async def stream_agent_run_events(run_id: str) -> StreamingResponse:
    from services.agent.app.core.events.event_bus import get_agent_event_bus
    bus = get_agent_event_bus()
    
    async def event_generator():
        try:
            async for event in bus.subscribe(run_id):
                chunk = {
                    "run_id": event.run_id,
                    "event_type": event.event_type,
                    "payload": event.payload,
                    "timestamp": event.timestamp,
                }
                yield f"data: {json.dumps(chunk)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            
    return StreamingResponse(event_generator(), media_type="text/event-stream")
