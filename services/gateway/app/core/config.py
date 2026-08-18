from functools import lru_cache

from pydantic import Field

from shared.config.settings import Settings


class GatewaySettings(Settings):
    """API Gateway specific settings and route mappings."""

    api_v1_prefix: str = Field(default="/api/v1", description="API Version 1 URL prefix")

    # Downstream Service Routing URLs
    agent_url: str = Field(default="http://agent:8001", validation_alias="AGENT_URL", description="Agent microservice URL")
    llm_url: str = Field(default="http://llm:8002", validation_alias="LLM_URL", description="LLM microservice URL")
    repository_url: str = Field(default="http://repository:8003", validation_alias="REPOSITORY_URL", description="Repository microservice URL")
    retrieval_url: str = Field(default="http://retrieval:8004", validation_alias="RETRIEVAL_URL", description="Retrieval microservice URL")
    tools_url: str = Field(default="http://tools:8005", validation_alias="TOOLS_URL", description="Tools microservice URL")
    git_url: str = Field(default="http://git:8006", validation_alias="GIT_URL", description="Git microservice URL")
    evaluation_url: str = Field(default="http://evaluation:8007", validation_alias="EVALUATION_URL", description="Evaluation microservice URL")

    # Proxy Client Timeout
    proxy_timeout_seconds: float = Field(default=120.0, description="HTTP proxy timeout in seconds")


@lru_cache
def get_gateway_settings() -> GatewaySettings:
    """Cached Gateway settings accessor."""
    return GatewaySettings()
