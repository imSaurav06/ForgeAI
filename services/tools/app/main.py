from services.tools.app.api.routers.tools import router as tools_router
from services.tools.app.api.routers.terminal_ws import (
    pty_session_manager,
    ws_router as terminal_ws_router,
)
from shared.config.settings import get_settings
from shared.utils.app_factory import create_app


settings = get_settings()


app = create_app(
    service_name="tool-service",
    service_version="0.1.0",
    description=(
        "Tool Execution Service providing sandboxed workspace file operations, "
        "atomic patch execution with rollback, safe terminal runner, and "
        "quality runners."
    ),
    routers=[tools_router],
    enforce_internal_auth=True,
)


# WebSocket routes are registered directly
# (not via enforce_internal_auth middleware)
app.include_router(terminal_ws_router)


@app.on_event("startup")
async def start_pty_session_manager() -> None:
    await pty_session_manager.start_cleanup_worker()


@app.on_event("shutdown")
async def stop_pty_session_manager() -> None:
    await pty_session_manager.close_all()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "services.tools.app.main:app",
        host=settings.tool_service_host,
        port=settings.tool_service_port,
        reload=True,
    )