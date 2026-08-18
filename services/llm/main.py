from services.llm.app.main import app

__all__ = ["app"]

if __name__ == "__main__":
    import uvicorn

    from shared.config.settings import get_settings

    settings = get_settings()
    uvicorn.run(
        "services.llm.main:app",
        host=settings.llm_service_host,
        port=settings.llm_service_port,
        reload=True,
    )
