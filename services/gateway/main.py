from services.gateway.app.main import app

__all__ = ["app"]

if __name__ == "__main__":
    import uvicorn

    from shared.config.settings import get_settings

    settings = get_settings()
    uvicorn.run(
        "services.gateway.main:app",
        host=settings.gateway_host,
        port=settings.gateway_port,
        reload=True,
    )
