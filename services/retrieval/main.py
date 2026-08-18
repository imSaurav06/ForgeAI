from services.retrieval.app.main import app

__all__ = ["app"]

if __name__ == "__main__":
    import uvicorn

    from shared.config.settings import get_settings

    settings = get_settings()
    uvicorn.run(
        "services.retrieval.main:app",
        host=settings.retrieval_service_host,
        port=settings.retrieval_service_port,
        reload=True,
    )
