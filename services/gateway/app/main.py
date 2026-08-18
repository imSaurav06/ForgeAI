from fastapi import APIRouter

from services.gateway.app.api.middleware.auth import AuthMiddlewareScaffold
from services.gateway.app.api.middleware.rate_limit import RateLimitMiddleware
from services.gateway.app.api.routers import (
    agent_router,
    auth_router,
    filesystem_router,
    git_router,
    models_router,
    projects_router,
    repositories_router,
    search_router,
    ws_router,
)
from services.gateway.app.core.config import get_gateway_settings
from services.gateway.app.core.metrics import router as metrics_router
from services.gateway.app.services.health_aggregator import HealthAggregator
from shared.database.mongodb import close_mongodb_connection, init_mongodb_indexes
from shared.utils.app_factory import create_app

settings = get_gateway_settings()
health_aggregator = HealthAggregator(cache_ttl_seconds=5.0)

from shared.schemas.responses import SuccessResponse

# Create Version 1 API Master Router
v1_router = APIRouter(prefix=settings.api_v1_prefix)
v1_router.include_router(auth_router)
v1_router.include_router(projects_router)
v1_router.include_router(repositories_router)
v1_router.include_router(filesystem_router)
v1_router.include_router(agent_router)
v1_router.include_router(models_router)
v1_router.include_router(git_router)
v1_router.include_router(search_router)
v1_router.include_router(ws_router)


@v1_router.get(
    "/health/aggregate",
    summary="Get Aggregated System Health",
)
async def get_system_health_endpoint():
    system_health = await health_aggregator.get_system_health()
    return SuccessResponse(data=system_health, message="System health retrieved")


async def get_aggregated_health():
    """Health check callback querying all backend microservices with TTL cache."""
    system_health = await health_aggregator.get_system_health()
    return system_health.model_dump()


app = create_app(
    service_name="api-gateway",
    service_version="0.1.0",
    description="API Gateway single public entry point providing authentication, resilience, and metrics.",
    routers=[v1_router, metrics_router],
    startup_hooks=[init_mongodb_indexes],
    shutdown_hooks=[close_mongodb_connection],
    health_details_provider=get_aggregated_health,
)

# Add Gateway Production Middlewares
app.add_middleware(RateLimitMiddleware, requests_per_minute=120)
app.add_middleware(AuthMiddlewareScaffold)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "services.gateway.app.main:app",
        host=settings.gateway_host,
        port=settings.gateway_port,
        reload=True,
    )
