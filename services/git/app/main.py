from services.git.app.api.routers.git import router as git_router
from shared.config.settings import get_settings
from shared.utils.app_factory import create_app

settings = get_settings()

app = create_app(
    service_name="git-service",
    service_version="0.1.0",
    description="Git Service providing version-control status, diff generation, commit history logs, branch checkout, commits, and file restoration.",
    routers=[git_router],
    enforce_internal_auth=True,
)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "services.git.app.main:app",
        host=settings.git_service_host,
        port=settings.git_service_port,
        reload=True,
    )
