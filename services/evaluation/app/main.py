from services.evaluation.app.api.routers.evaluation import router as evaluation_router
from shared.config.settings import get_settings
from shared.database.mongodb import check_mongodb_health
from shared.utils.app_factory import create_app

settings = get_settings()


async def health_details_provider() -> dict:
    mongo_health = await check_mongodb_health()
    return {"mongodb": mongo_health}


app = create_app(
    service_name="evaluation-service",
    service_version="0.1.0",
    description="Evaluation Service responsible for measuring platform accuracy, reliability, token usage, latency, running benchmark suites, and generating evaluation reports.",
    routers=[evaluation_router],
    health_details_provider=health_details_provider,
    enforce_internal_auth=True,
)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "services.evaluation.app.main:app",
        host=settings.evaluation_service_host,
        port=settings.evaluation_service_port,
        reload=True,
    )
