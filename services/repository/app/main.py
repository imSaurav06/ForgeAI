from services.repository.app.api.routers.repository import router as repository_router
from shared.config.settings import get_settings
from shared.database.mongodb import check_mongodb_health
from shared.utils.app_factory import create_app

settings = get_settings()


async def health_details_provider() -> dict:
    mongo_health = await check_mongodb_health()
    return {"mongodb": mongo_health}


app = create_app(
    service_name="repository-service",
    service_version="0.1.0",
    description="Repository Intelligence Service responsible for code scanning, AST symbol parsing, language detection, and dependency graph analysis.",
    routers=[repository_router],
    health_details_provider=health_details_provider,
    enforce_internal_auth=True,
)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "services.repository.app.main:app",
        host=settings.repository_service_host,
        port=settings.repository_service_port,
        reload=True,
    )
