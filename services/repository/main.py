from services.repository.app.main import app

__all__ = ["app"]

if __name__ == "__main__":
    import uvicorn

    from shared.config.settings import get_settings

    settings = get_settings()
    uvicorn.run(
        "services.repository.main:app",
        host=settings.repository_service_host,
        port=settings.repository_service_port,
        reload=True,
    )
