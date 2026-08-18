from services.llm.app.api.routers.llm import router as llm_router
from shared.config.settings import get_settings
from shared.utils.app_factory import create_app

settings = get_settings()


def health_details_provider() -> dict:
    return {"ollama": {"url": settings.ollama_url}}


app = create_app(
    service_name="llm-service",
    service_version="0.1.0",
    description="LLM Service responsible for real Ollama model inference, active model switching, prompt compilation, and token streaming.",
    routers=[llm_router],
    health_details_provider=health_details_provider,
    enforce_internal_auth=True,
)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "services.llm.app.main:app",
        host=settings.llm_service_host,
        port=settings.llm_service_port,
        reload=True,
    )
