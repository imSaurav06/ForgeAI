from collections import defaultdict

from fastapi import APIRouter, Response


class GatewayMetricsRegistry:
    """Prometheus-compatible metrics collector for API Gateway."""

    def __init__(self) -> None:
        self.request_counts: dict[tuple[str, str, int], int] = defaultdict(int)
        self.error_counts: dict[tuple[str, str, int], int] = defaultdict(int)
        self.downstream_failures: dict[str, int] = defaultdict(int)
        self.request_latencies: dict[tuple[str, str], list[float]] = defaultdict(list)
        self.active_connections: int = 0

    def record_request(self, method: str, path: str, status_code: int, duration_sec: float) -> None:
        """Record HTTP request metric."""
        key = (method, path, status_code)
        self.request_counts[key] += 1

        if status_code >= 400:
            self.error_counts[key] += 1

        self.request_latencies[(method, path)].append(duration_sec)
        # Keep maximum 1000 recent samples per endpoint
        if len(self.request_latencies[(method, path)]) > 1000:
            self.request_latencies[(method, path)] = self.request_latencies[(method, path)][-1000:]

    def record_downstream_failure(self, service_name: str) -> None:
        """Record a downstream microservice invocation failure."""
        self.downstream_failures[service_name] += 1

    def increment_active_connections(self) -> None:
        self.active_connections += 1

    def decrement_active_connections(self) -> None:
        self.active_connections = max(0, self.active_connections - 1)

    def generate_prometheus_text(self) -> str:
        """Generate Prometheus exposition text format."""
        lines = []

        # HELP and TYPE for gateway_requests_total
        lines.append("# HELP gateway_requests_total Total number of HTTP requests handled by the Gateway.")
        lines.append("# TYPE gateway_requests_total counter")
        for (method, path, status_code), count in self.request_counts.items():
            lines.append(f'gateway_requests_total{{method="{method}",path="{path}",status="{status_code}"}} {count}')

        # HELP and TYPE for gateway_errors_total
        lines.append("# HELP gateway_errors_total Total number of HTTP request errors.")
        lines.append("# TYPE gateway_errors_total counter")
        for (method, path, status_code), count in self.error_counts.items():
            lines.append(f'gateway_errors_total{{method="{method}",path="{path}",status="{status_code}"}} {count}')

        # HELP and TYPE for gateway_downstream_failures_total
        lines.append("# HELP gateway_downstream_failures_total Total downstream service failure count.")
        lines.append("# TYPE gateway_downstream_failures_total counter")
        for service_name, count in self.downstream_failures.items():
            lines.append(f'gateway_downstream_failures_total{{service="{service_name}"}} {count}')

        # HELP and TYPE for gateway_active_connections
        lines.append("# HELP gateway_active_connections Current active connections.")
        lines.append("# TYPE gateway_active_connections gauge")
        lines.append(f"gateway_active_connections {self.active_connections}")

        # HELP and TYPE for average latency
        lines.append("# HELP gateway_request_duration_seconds_avg Average request duration in seconds.")
        lines.append("# TYPE gateway_request_duration_seconds_avg gauge")
        for (method, path), latencies in self.request_latencies.items():
            if latencies:
                avg_lat = sum(latencies) / len(latencies)
                lines.append(f'gateway_request_duration_seconds_avg{{method="{method}",path="{path}"}} {avg_lat:.6f}')

        return "\n".join(lines) + "\n"


_metrics_registry_instance: GatewayMetricsRegistry | None = None


def get_metrics_registry() -> GatewayMetricsRegistry:
    """Accessor for global GatewayMetricsRegistry."""
    global _metrics_registry_instance
    if _metrics_registry_instance is None:
        _metrics_registry_instance = GatewayMetricsRegistry()
    return _metrics_registry_instance


router = APIRouter(tags=["Metrics"])


@router.get("/metrics", summary="Prometheus Metrics Endpoint", description="Exposes Gateway performance, error rates, and connection metrics in Prometheus text format.")
async def get_metrics() -> Response:
    registry = get_metrics_registry()
    content = registry.generate_prometheus_text()
    return Response(content=content, media_type="text/plain; version=0.0.4; charset=utf-8")
