from services.git.app.main import app

__all__ = ["app"]

if __name__ == "__main__":
    import uvicorn

    from shared.config.settings import get_settings

    settings = get_settings()
    uvicorn.run(
        "services.git.main:app",
        host=settings.git_service_host,
        port=settings.git_service_port,
        reload=True,
    )
