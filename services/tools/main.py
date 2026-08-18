from services.tools.app.main import app

__all__ = ["app"]

if __name__ == "__main__":
    import uvicorn

    from shared.config.settings import get_settings

    settings = get_settings()
    uvicorn.run(
        "services.tools.main:app",
        host=settings.tool_service_host,
        port=settings.tool_service_port,
        reload=True,
    )
