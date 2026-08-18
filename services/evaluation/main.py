from services.evaluation.app.main import app

__all__ = ["app"]

if __name__ == "__main__":
    import uvicorn

    from shared.config.settings import get_settings

    settings = get_settings()
    uvicorn.run(
        "services.evaluation.main:app",
        host=settings.evaluation_service_host,
        port=settings.evaluation_service_port,
        reload=True,
    )
