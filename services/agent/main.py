from services.agent.app.main import app

__all__ = ["app"]

if __name__ == "__main__":
    import uvicorn

    from shared.config.settings import get_settings

    settings = get_settings()
    uvicorn.run(
        "services.agent.main:app",
        host=settings.agent_service_host,
        port=settings.agent_service_port,
        reload=True,
    )
