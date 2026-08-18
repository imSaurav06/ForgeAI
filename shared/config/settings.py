from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Central environment-driven configuration settings for ForgeAI platform services.
    All attributes support overrides via environment variables or .env file.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Core Application Settings
    environment: Literal["development", "testing", "production"] = Field(
        default="development", description="Execution environment mode"
    )
    log_level: str = Field(default="INFO", description="Logging output level")
    secret_key: str = Field(
        default="dev_secret_key_forge_ai_2026_change_in_production",
        description="Secret key for security operations",
    )
    jwt_secret: str = Field(
        default="forge_ai_jwt_secret_key_2026_secure",
        description="Secret key for JWT signature verification",
    )
    jwt_algorithm: str = Field(default="HS256", description="JWT signing algorithm")
    jwt_expiration_minutes: int = Field(default=60, description="JWT token validity in minutes")
    internal_service_token: str = Field(
        default="forge_internal_hmac_secret_2026",
        description="Shared secret for internal gateway to microservice authentication",
    )
    allow_dev_auth_fallback: bool = Field(
        default=False,
        description="Whether unauthenticated requests default to local dev user (must be False for production security)",
    )
    service_name: str = Field(
        default="forge-service", description="Current microservice identifier"
    )
    service_version: str = Field(
        default="0.1.0", description="Current microservice release version"
    )

    # Gateway Service
    gateway_port: int = Field(default=8000, description="API Gateway listener port")
    gateway_host: str = Field(default="0.0.0.0", description="API Gateway host binding")

    # Agent Service
    agent_service_port: int = Field(default=8001, description="Agent service port")
    agent_service_host: str = Field(default="0.0.0.0", description="Agent service host")
    agent_service_url: str = Field(
        default="http://localhost:8001", description="Agent service base URL"
    )

    # LLM Service
    llm_service_port: int = Field(default=8002, description="LLM service port")
    llm_service_host: str = Field(default="0.0.0.0", description="LLM service host")
    llm_service_url: str = Field(
        default="http://localhost:8002", description="LLM service base URL"
    )
    ollama_url: str = Field(
        default="http://localhost:11434", description="Ollama API base URL"
    )
    default_quality_model: str = Field(
        default="qwen2.5-coder:3b-instruct-q4_0", description="Primary coding model"
    )
    default_fast_model: str = Field(
        default="qwen2.5-coder:3b-instruct-q4_0", description="Fast response model"
    )

    # Repository Service
    repository_service_port: int = Field(default=8003, description="Repository service port")
    repository_service_host: str = Field(default="0.0.0.0", description="Repository host")
    repository_service_url: str = Field(
        default="http://localhost:8003", description="Repository service URL"
    )

    # Retrieval Service
    retrieval_service_port: int = Field(default=8004, description="Retrieval service port")
    retrieval_service_host: str = Field(default="0.0.0.0", description="Retrieval host")
    retrieval_service_url: str = Field(
        default="http://localhost:8004", description="Retrieval service URL"
    )
    qdrant_host: str = Field(default="localhost", description="Qdrant vector database host")
    qdrant_port: int = Field(default=6333, description="Qdrant vector database port")
    qdrant_url: str | None = Field(default=None, description="Qdrant vector database URL override")
    qdrant_location: str | None = Field(
        default=":memory:", description="Qdrant location override (e.g. :memory: for embedded real engine)"
    )
    embedding_model_name: str = Field(
        default="BAAI/bge-small-en-v1.5", description="Local pretrained semantic embedding model identifier"
    )
    embedding_dimension: int = Field(
        default=384, description="Vector dimension produced by local semantic embedding model"
    )
    qdrant_collection_name: str = Field(
        default="forge_ai_code", description="Default vector collection"
    )

    # Tool Service
    tool_service_port: int = Field(default=8005, description="Tool execution service port")
    tool_service_host: str = Field(default="0.0.0.0", description="Tool service host")
    tool_service_url: str = Field(
        default="http://localhost:8005", description="Tool service base URL"
    )
    workspace_root: str = Field(
        default="./workspace", description="Safe sandbox workspace directory"
    )

    # Git Service
    git_service_port: int = Field(default=8006, description="Git service port")
    git_service_host: str = Field(default="0.0.0.0", description="Git service host")
    git_service_url: str = Field(
        default="http://localhost:8006", description="Git service base URL"
    )

    # Evaluation Service
    evaluation_service_port: int = Field(
        default=8007, description="Evaluation service port"
    )
    evaluation_service_host: str = Field(
        default="0.0.0.0", description="Evaluation host"
    )
    evaluation_service_url: str = Field(
        default="http://localhost:8007", description="Evaluation service base URL"
    )

    # Database Settings
    mongodb_uri: str = Field(
        default="mongodb://localhost:27017", description="MongoDB connection string"
    )
    mongodb_database: str = Field(
        default="forge_ai_db", description="MongoDB database name"
    )

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @property
    def is_testing(self) -> bool:
        return self.environment == "testing"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance accessor."""
    return Settings()
