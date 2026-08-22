import os
from typing import Literal

from services.gateway.app.core.config import get_gateway_settings
from shared.exceptions.handlers import ForgeException


class ServiceRegistry:
    """Central registry managing downstream microservices and health status."""

    def __init__(self) -> None:
        self.settings = get_gateway_settings()
        is_docker = os.path.exists("/.dockerenv") or os.environ.get("RUNNING_IN_DOCKER") == "true"
        
        def _resolve_url(port: int, default_docker_url: str) -> str:
            if not is_docker and ("://" in default_docker_url and "localhost" not in default_docker_url and "127.0.0.1" not in default_docker_url):
                return f"http://localhost:{port}"
            return default_docker_url

        self._service_urls: dict[str, str] = {
            "agent": _resolve_url(8001, self.settings.agent_url),
            "llm": _resolve_url(8002, self.settings.llm_url),
            "repository": _resolve_url(8003, self.settings.repository_url),
            "retrieval": _resolve_url(8004, self.settings.retrieval_url),
            "tools": _resolve_url(8005, self.settings.tools_url),
            "git": _resolve_url(8006, self.settings.git_url),
            "evaluation": _resolve_url(8007, self.settings.evaluation_url),
        }
        self._service_status: dict[str, Literal["healthy", "degraded", "offline"]] = {
            name: "healthy" for name in self._service_urls
        }

    def register_service(self, name: str, url: str) -> None:
        """Register or update a microservice base URL."""
        self._service_urls[name] = url
        self._service_status[name] = "healthy"

    def get_service_url(self, service_name: str) -> str:
        """Resolve base URL for a registered microservice."""
        url = self._service_urls.get(service_name.lower())
        if not url:
            raise ForgeException(
                message=f"Service '{service_name}' is not registered in Gateway Service Registry",
                code="SERVICE_NOT_REGISTERED",
                status_code=404,
            )
        return url

    def set_service_status(self, service_name: str, status: Literal["healthy", "degraded", "offline"]) -> None:
        """Update tracked health status of a service."""
        if service_name.lower() in self._service_status:
            self._service_status[service_name.lower()] = status

    def get_service_status(self, service_name: str) -> str:
        """Retrieve tracked health status of a service."""
        return self._service_status.get(service_name.lower(), "offline")

    def list_services(self) -> dict[str, dict[str, str]]:
        """Return dict of all registered services with URLs and status."""
        return {
            name: {"url": self._service_urls[name], "status": self._service_status[name]}
            for name in self._service_urls
        }


# Singleton service registry instance
_registry_instance: ServiceRegistry | None = None


def get_service_registry() -> ServiceRegistry:
    """Accessor for global ServiceRegistry instance."""
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = ServiceRegistry()
    return _registry_instance
