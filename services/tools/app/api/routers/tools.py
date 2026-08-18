from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from services.tools.app.schemas.tool_schemas import (
    ApplyPatchRequest,
    DeleteFileRequest,
    ReadFileRequest,
    ReadFileResponse,
    RunCommandRequest,
    RunQualityToolRequest,
    RunTestRequest,
    SearchFilesRequest,
    TerminalExecuteRequest,
    TerminalInputRequest,
    TerminalInterruptRequest,
    TerminalSessionRequest,
    WriteFileRequest,
)
from services.tools.app.services.tool_service import ToolExecutionService
from shared.schemas.responses import ErrorResponse, SuccessResponse


router = APIRouter(
    prefix="/internal/v1/tools",
    tags=["Tool Execution Service"],
)

tool_service = ToolExecutionService()


@router.post(
    "/read-file",
    response_model=SuccessResponse[ReadFileResponse],
    summary="Read File Content",
    description="Reads content of a target file inside the selected repository.",
    responses={
        200: {
            "model": SuccessResponse[ReadFileResponse],
            "description": "File content read",
        },
        404: {
            "model": ErrorResponse,
            "description": "File or repository not found",
        },
    },
)
async def read_file(
    payload: ReadFileRequest,
) -> SuccessResponse[ReadFileResponse]:
    res = tool_service.read_file(
        path=payload.path,
        start_line=payload.start_line,
        end_line=payload.end_line,
        repository_id=payload.repository_id,
    )

    return SuccessResponse(
        data=ReadFileResponse(**res),
        message="File read successfully",
    )


@router.post(
    "/write-file",
    response_model=SuccessResponse[dict[str, Any]],
    summary="Write File Content",
    description="Writes text content to a target file inside the selected repository.",
    responses={
        200: {
            "model": SuccessResponse[dict[str, Any]],
            "description": "File written successfully",
        },
        404: {
            "model": ErrorResponse,
            "description": "Repository not found",
        },
    },
)
async def write_file(
    payload: WriteFileRequest,
) -> SuccessResponse[dict[str, Any]]:
    res = tool_service.write_file(
        path=payload.path,
        content=payload.content,
        repository_id=payload.repository_id,
    )

    return SuccessResponse(
        data=res,
        message="File written successfully",
    )


@router.post(
    "/search",
    response_model=SuccessResponse[list[dict[str, Any]]],
    summary="Search Files",
    description="Searches files inside the selected repository.",
    responses={
        200: {
            "model": SuccessResponse[list[dict[str, Any]]],
            "description": "File search results",
        },
        404: {
            "model": ErrorResponse,
            "description": "Repository not found",
        },
    },
)
async def search_files(
    payload: SearchFilesRequest,
) -> SuccessResponse[list[dict[str, Any]]]:
    matches = tool_service.search_files(
        pattern=payload.pattern,
        repository_id=payload.repository_id,
        search_dir=payload.path,
    )

    return SuccessResponse(
        data=matches,
        message="File search completed",
    )


@router.post(
    "/apply-patch",
    response_model=SuccessResponse[dict[str, Any]],
    summary="Apply Atomic Multi-File Patch",
    description=(
        "Executes atomic patch creation, modification, and deletion "
        "inside the selected repository with automatic rollback on failure."
    ),
    responses={
        200: {
            "model": SuccessResponse[dict[str, Any]],
            "description": "Patch applied successfully",
        },
        400: {
            "model": ErrorResponse,
            "description": "Patch application error and rolled back",
        },
        404: {
            "model": ErrorResponse,
            "description": "Repository not found",
        },
    },
)
async def apply_patch(
    payload: ApplyPatchRequest,
) -> SuccessResponse[dict[str, Any]]:
    res = tool_service.apply_patch(
        repository_id=payload.repository_id,
        files_to_create=payload.files_to_create,
        files_to_modify=payload.files_to_modify,
        files_to_delete=payload.files_to_delete,
    )

    return SuccessResponse(
        data=res,
        message="Patch applied successfully",
    )


@router.post(
    "/delete-file",
    response_model=SuccessResponse[dict[str, Any]],
    summary="Delete File",
    description="Deletes target file from the selected repository.",
    responses={
        200: {
            "model": SuccessResponse[dict[str, Any]],
            "description": "File deleted",
        },
        404: {
            "model": ErrorResponse,
            "description": "File or repository not found",
        },
    },
)
async def delete_file(
    payload: DeleteFileRequest,
) -> SuccessResponse[dict[str, Any]]:
    res = tool_service.delete_file(
        path=payload.path,
        repository_id=payload.repository_id,
    )

    return SuccessResponse(
        data=res,
        message="File deleted successfully",
    )


@router.post(
    "/run-command",
    response_model=SuccessResponse[dict[str, Any]],
    summary="Run Sandboxed Terminal Command",
    description=(
        "Executes a one-shot terminal command safely inside the "
        "selected repository with timeout and secret masking."
    ),
    responses={
        200: {
            "model": SuccessResponse[dict[str, Any]],
            "description": "Command executed",
        },
        401: {
            "model": ErrorResponse,
            "description": "Dangerous command blocked",
        },
        404: {
            "model": ErrorResponse,
            "description": "Repository not found",
        },
    },
)
async def run_command(
    payload: RunCommandRequest,
) -> SuccessResponse[dict[str, Any]]:
    res = await tool_service.run_command(
        command=payload.command,
        cwd=payload.cwd,
        timeout_sec=payload.timeout_sec,
        repository_id=payload.repository_id,
    )

    return SuccessResponse(
        data=res,
        message="Command executed",
    )


@router.post(
    "/terminal/session",
    response_model=SuccessResponse[dict[str, Any]],
    summary="Create Persistent Terminal Session",
    description=(
        "Creates or reuses a persistent PTY terminal session "
        "bound to the selected repository."
    ),
    responses={
        200: {
            "model": SuccessResponse[dict[str, Any]],
            "description": "Terminal session created or reused",
        },
        403: {
            "model": ErrorResponse,
            "description": "Terminal session ownership rejected",
        },
        404: {
            "model": ErrorResponse,
            "description": "Repository not found",
        },
    },
)
async def create_terminal_session(
    payload: TerminalSessionRequest,
) -> SuccessResponse[dict[str, Any]]:
    res = await tool_service.create_terminal_session(
        session_id=payload.session_id,
        repository_id=payload.repository_id,
        workspace=payload.workspace,
        shell=payload.shell,
        cols=payload.cols,
        rows=payload.rows,
    )

    return SuccessResponse(
        data=res,
        message="Terminal session ready",
    )


@router.post(
    "/terminal/input",
    response_model=SuccessResponse[dict[str, Any]],
    summary="Write Persistent Terminal Input",
    description="Writes input into an existing persistent PTY terminal session.",
    responses={
        200: {
            "model": SuccessResponse[dict[str, Any]],
            "description": "Terminal input written",
        },
        404: {
            "model": ErrorResponse,
            "description": "Terminal session not found",
        },
    },
)
async def terminal_input(
    payload: TerminalInputRequest,
) -> SuccessResponse[dict[str, Any]]:
    res = await tool_service.write_terminal_input(
        session_id=payload.session_id,
        data=payload.data,
    )

    return SuccessResponse(
        data=res,
        message="Terminal input written",
    )


@router.post(
    "/terminal/interrupt",
    response_model=SuccessResponse[dict[str, Any]],
    summary="Interrupt Persistent Terminal",
    description="Sends SIGINT to an existing persistent PTY terminal session.",
    responses={
        200: {
            "model": SuccessResponse[dict[str, Any]],
            "description": "Terminal interrupted",
        },
        404: {
            "model": ErrorResponse,
            "description": "Terminal session not found",
        },
    },
)
async def terminal_interrupt(
    payload: TerminalInterruptRequest,
) -> SuccessResponse[dict[str, Any]]:
    res = await tool_service.interrupt_terminal(
        session_id=payload.session_id,
    )

    return SuccessResponse(
        data=res,
        message="Terminal interrupted",
    )


@router.post(
    "/terminal/execute",
    response_model=SuccessResponse[dict[str, Any]],
    summary="Execute Persistent Terminal Command",
    description=(
        "Executes a command inside an existing persistent PTY "
        "session and waits for command completion."
    ),
    responses={
        200: {
            "model": SuccessResponse[dict[str, Any]],
            "description": "Persistent terminal command completed",
        },
        404: {
            "model": ErrorResponse,
            "description": "Terminal session not found",
        },
        408: {
            "model": ErrorResponse,
            "description": "Terminal command timed out",
        },
    },
)
async def terminal_execute(
    payload: TerminalExecuteRequest,
) -> SuccessResponse[dict[str, Any]]:
    res = await tool_service.execute_terminal_command(
        session_id=payload.session_id,
        command=payload.command,
        timeout_sec=payload.timeout_sec,
    )

    return SuccessResponse(
        data=res,
        message="Terminal command completed",
    )


@router.post(
    "/run-test",
    response_model=SuccessResponse[dict[str, Any]],
    summary="Run Pytest Suite",
    description=(
        "Executes pytest inside the selected repository and returns "
        "structured JSON results."
    ),
    responses={
        200: {
            "model": SuccessResponse[dict[str, Any]],
            "description": "Tests executed",
        },
        404: {
            "model": ErrorResponse,
            "description": "Repository not found",
        },
    },
)
async def run_test(
    payload: RunTestRequest,
) -> SuccessResponse[dict[str, Any]]:
    res = await tool_service.run_test(
        test_path=payload.test_path,
        timeout_sec=payload.timeout_sec,
        repository_id=payload.repository_id,
    )

    return SuccessResponse(
        data=res,
        message="Tests executed",
    )


@router.post(
    "/run-build",
    response_model=SuccessResponse[dict[str, Any]],
    summary="Run Build",
    description="Executes build command inside the selected repository.",
    responses={
        200: {
            "model": SuccessResponse[dict[str, Any]],
            "description": "Build executed",
        },
        404: {
            "model": ErrorResponse,
            "description": "Repository not found",
        },
    },
)
async def run_build(
    payload: RunQualityToolRequest,
) -> SuccessResponse[dict[str, Any]]:
    res = await tool_service.run_build(
        command=payload.command,
        repository_id=payload.repository_id,
    )

    return SuccessResponse(
        data=res,
        message="Build executed",
    )


@router.post(
    "/run-linter",
    response_model=SuccessResponse[dict[str, Any]],
    summary="Run Linter",
    description="Executes ruff linter check inside the selected repository.",
    responses={
        200: {
            "model": SuccessResponse[dict[str, Any]],
            "description": "Linter executed",
        },
        404: {
            "model": ErrorResponse,
            "description": "Repository not found",
        },
    },
)
async def run_linter(
    payload: RunQualityToolRequest,
) -> SuccessResponse[dict[str, Any]]:
    res = await tool_service.run_linter(
        target_path=payload.target_path,
        repository_id=payload.repository_id,
    )

    return SuccessResponse(
        data=res,
        message="Linter executed",
    )


@router.post(
    "/run-formatter",
    response_model=SuccessResponse[dict[str, Any]],
    summary="Run Formatter",
    description="Executes ruff formatter inside the selected repository.",
    responses={
        200: {
            "model": SuccessResponse[dict[str, Any]],
            "description": "Formatter executed",
        },
        404: {
            "model": ErrorResponse,
            "description": "Repository not found",
        },
    },
)
async def run_formatter(
    payload: RunQualityToolRequest,
) -> SuccessResponse[dict[str, Any]]:
    res = await tool_service.run_formatter(
        target_path=payload.target_path,
        repository_id=payload.repository_id,
    )

    return SuccessResponse(
        data=res,
        message="Formatter executed",
    )