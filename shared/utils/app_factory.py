from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.openapi.utils import get_openapi

from shared.config.settings import get_settings
from shared.exceptions.handlers import register_exception_handlers
from shared.logging.logger import setup_logger
from shared.middleware.cors import setup_cors
from shared.middleware.logging import RequestLoggingMiddleware
from shared.middleware.request_id import RequestIDMiddleware
from shared.schemas.responses import HealthResponse


def create_app(
    service_name: str,
    service_version: str = "0.1.0",
    description: str = "ForgeAI Microservice API",
    routers: list[APIRouter] | None = None,
    startup_hooks: list[Callable[[], None | AsyncGenerator[None, None]]] | None = None,
    shutdown_hooks: list[Callable[[], None | AsyncGenerator[None, None]]] | None = None,
    health_details_provider: Callable[[], dict] | None = None,
    enforce_internal_auth: bool = False,
) -> FastAPI:
    """
    Factory creating a standardized FastAPI microservice application for ForgeAI.
    Initializes middleware, Swagger/OpenAPI docs, logging, exception handlers,
    lifespan management, and standard /health route.
    """
    settings = get_settings()

    # Initialize structured loguru logger
    setup_logger(service_name=service_name, log_level=settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        # Startup phase
        if startup_hooks:
            for hook in startup_hooks:
                res = hook()
                if hasattr(res, "__await__"):
                    await res

        yield

        # Shutdown phase
        if shutdown_hooks:
            for hook in shutdown_hooks:
                res = hook()
                if hasattr(res, "__await__"):
                    await res

    app = FastAPI(
        title=f"ForgeAI - {service_name.replace('-', ' ').title()}",
        description=description,
        version=service_version,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # Attach Core Middleware
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
    if enforce_internal_auth:
        from shared.middleware.internal_auth import InternalAuthMiddleware

        app.add_middleware(InternalAuthMiddleware)
    setup_cors(app)

    # Register Exception Handlers
    register_exception_handlers(app)

    # Standard Health Check Endpoint (Task 09)
    @app.get(
        "/health",
        response_model=HealthResponse,
        summary="Service Health Check",
        description="Returns current microservice status, version, and health metrics.",
        tags=["Health"],
    )
    async def health_check() -> HealthResponse:
        import inspect

        details = None
        if health_details_provider:
            if inspect.iscoroutinefunction(health_details_provider):
                details = await health_details_provider()
            else:
                details = health_details_provider()

        overall_status = "healthy"
        if details:
            for dep_info in details.values():
                if isinstance(dep_info, dict) and dep_info.get("status") in ("unhealthy", "degraded"):
                    overall_status = dep_info["status"]
                    break

        return HealthResponse(
            service=service_name,
            status=overall_status,
            version=service_version,
            details=details,
        )

    # Include User-supplied Routers
    if routers:
        for router in routers:
            app.include_router(router)

    # Custom OpenAPI Schema Customization
    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        openapi_schema = get_openapi(
            title=f"ForgeAI - {service_name.replace('-', ' ').title()}",
            version=service_version,
            description=f"{description}\n\n*Part of the ForgeAI Local AI Software Engineering Platform.*",
            routes=app.routes,
        )
        openapi_schema["info"]["x-service-name"] = service_name
        app.openapi_schema = openapi_schema
        return app.openapi_schema

    app.openapi = custom_openapi

    return app
