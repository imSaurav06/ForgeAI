import asyncio
import time

import httpx

from services.gateway.app.core.config import get_gateway_settings
from services.gateway.app.schemas.health import ServiceHealthItem, SystemHealthResponse
from shared.logging.logger import logger


class HealthAggregator:
    """Service to aggregate health status across all 8 microservices with in-memory TTL caching."""

    def __init__(self, cache_ttl_seconds: float = 5.0) -> None:
        self.settings = get_gateway_settings()
        self.cache_ttl_seconds = cache_ttl_seconds
        self._cached_health: SystemHealthResponse | None = None
        self._last_check_time: float = 0.0
        self._lock = asyncio.Lock()

    async def check_service_health(self, service_name: str, url: str) -> ServiceHealthItem:
        """Ping a single service's GET /health endpoint."""
        health_url = f"{url.rstrip('/')}/health"
        start_time = time.perf_counter()

        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(health_url)
                latency_ms = (time.perf_counter() - start_time) * 1000

                if resp.status_code == 200:
                    data = resp.json()
                    return ServiceHealthItem(
                        service_name=service_name,
                        status=data.get("status", "healthy"),
                        version=data.get("version", "0.1.0"),
                        url=url,
                        latency_ms=round(latency_ms, 2),
                    )
                else:
                    return ServiceHealthItem(
                        service_name=service_name,
                        status="degraded",
                        version=None,
                        url=url,
                        latency_ms=round(latency_ms, 2),
                        error=f"Returned status code {resp.status_code}",
                    )
        except Exception as err:
            latency_ms = (time.perf_counter() - start_time) * 1000
            logger.debug(f"Health check failed for {service_name} at {url}: {err}")
            return ServiceHealthItem(
                service_name=service_name,
                status="offline",
                version=None,
                url=url,
                latency_ms=round(latency_ms, 2),
                error=str(err),
            )

    async def get_system_health(self, force_refresh: bool = False) -> SystemHealthResponse:
        """Retrieve aggregated health status with TTL caching."""
        now = time.time()

        if not force_refresh and self._cached_health and (now - self._last_check_time < self.cache_ttl_seconds):
            return self._cached_health

        async with self._lock:
            # Double check inside lock
            if not force_refresh and self._cached_health and (time.time() - self._last_check_time < self.cache_ttl_seconds):
                return self._cached_health

            service_targets = {
                "gateway": f"http://localhost:{self.settings.gateway_port}",
                "agent": self.settings.agent_url,
                "llm": self.settings.llm_url,
                "repository": self.settings.repository_url,
                "retrieval": self.settings.retrieval_url,
                "tools": self.settings.tools_url,
                "git": self.settings.git_url,
                "evaluation": self.settings.evaluation_url,
            }

            tasks = [
                self.check_service_health(name, target_url)
                for name, target_url in service_targets.items()
            ]

            results = await asyncio.gather(*tasks)
            services_map = {item.service_name: item for item in results}

            statuses = [item.status for item in services_map.values()]
            if all(s == "healthy" for s in statuses):
                overall_status = "healthy"
            elif any(s == "healthy" for s in statuses):
                overall_status = "degraded"
            else:
                overall_status = "unhealthy"

            self._cached_health = SystemHealthResponse(
                status=overall_status,
                services=services_map,
            )
            self._last_check_time = time.time()
            return self._cached_health
