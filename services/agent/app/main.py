from services.agent.app.api.routers.agent import router as agent_router
from shared.config.settings import get_settings
from shared.database.mongodb import check_mongodb_health
from shared.utils.app_factory import create_app

settings = get_settings()


async def health_details_provider() -> dict:
    mongo_health = await check_mongodb_health()
    return {"mongodb": mongo_health}


app = create_app(
    service_name="agent-service",
    service_version="0.1.0",
    description="Agent Service orchestrating Repository Intelligence, Retrieval, LLM, Tool Execution, and Git into autonomous software engineering workflows.",
    routers=[agent_router],
    health_details_provider=health_details_provider,
    enforce_internal_auth=True,
)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "services.agent.app.main:app",
        host=settings.agent_service_host,
        port=settings.agent_service_port,
        reload=True,
    )
