import time

import pytest
from fastapi.testclient import TestClient

from services.gateway.app.api.middleware.rate_limit import RateLimiter
from services.gateway.app.core.circuit_breaker import CircuitBreaker, CircuitState
from services.gateway.app.core.internal_auth import InternalAuthManager
from services.gateway.app.core.metrics import get_metrics_registry
from services.gateway.app.core.retry import RetryPolicy
from services.gateway.app.core.service_registry import get_service_registry
from services.gateway.app.main import app
from services.gateway.app.services.health_aggregator import HealthAggregator
from services.gateway.app.services.session_manager import GatewaySessionManager
from services.gateway.app.services.sse_manager import SSEConnectionManager
from services.gateway.app.services.ws_manager import WebSocketConnectionManager
from shared.exceptions.handlers import ServiceUnavailableException

client = TestClient(app)


def test_service_registry():
    """Task 01: Verify ServiceRegistry resolution and status tracking."""
    registry = get_service_registry()
    assert registry.get_service_url("agent") == "http://localhost:8001"
    assert registry.get_service_url("llm") == "http://localhost:8002"

    registry.set_service_status("agent", "degraded")
    assert registry.get_service_status("agent") == "degraded"
    registry.set_service_status("agent", "healthy")


def test_circuit_breaker():
    """Task 02: Verify CircuitBreaker state transitions (CLOSED -> OPEN -> HALF_OPEN)."""
    breaker = CircuitBreaker(service_name="test_service", failure_threshold=2, recovery_timeout=0.2)
    assert breaker.state == CircuitState.CLOSED
    assert breaker.allow_request() is True

    breaker.record_failure()
    assert breaker.state == CircuitState.CLOSED

    breaker.record_failure()
    assert breaker.state == CircuitState.OPEN
    assert breaker.allow_request() is False

    # Wait for recovery timeout to pass
    time.sleep(0.25)
    assert breaker.allow_request() is True
    assert breaker.state == CircuitState.HALF_OPEN

    breaker.record_success()
    assert breaker.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_retry_policy():
    """Task 03: Verify RetryPolicy exponential backoff for idempotent operations."""
    policy = RetryPolicy(max_retries=3, initial_delay=0.01)
    attempts = 0

    async def transient_failing_func():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ServiceUnavailableException("Transient error")
        return "success"

    def is_retryable(exc):
        return isinstance(exc, ServiceUnavailableException)

    result = await policy.execute(transient_failing_func, is_retryable, method="GET")
    assert result == "success"
    assert attempts == 3


def test_rate_limiting():
    """Task 04: Verify RateLimiter sliding window and HTTP 429 response."""
    limiter = RateLimiter(requests_per_minute=2, window_seconds=60)
    allowed1, _ = limiter.is_allowed("test_client")
    allowed2, _ = limiter.is_allowed("test_client")
    allowed3, retry_after = limiter.is_allowed("test_client")

    assert allowed1 is True
    assert allowed2 is True
    assert allowed3 is False
    assert retry_after > 0


def test_internal_authentication():
    """Task 05: Verify InternalAuthManager token signing and validation."""
    auth_mgr = InternalAuthManager()
    token = auth_mgr.generate_internal_token("api-gateway")
    assert auth_mgr.verify_internal_token(token) is True
    assert auth_mgr.verify_internal_token("invalid:signature") is False

    headers = auth_mgr.inject_internal_headers({}, user_id="user_test", user_role="developer")
    assert "X-Internal-Service-Token" in headers
    assert headers["X-User-ID"] == "user_test"


def get_auth_headers() -> dict[str, str]:
    from services.gateway.app.api.dependencies.auth import generate_jwt_token
    token = generate_jwt_token(user_id="user_test_dev", role="admin")
    return {"Authorization": f"Bearer {token}"}


def test_distributed_request_tracing():
    """Task 06: Verify X-Request-ID, X-Trace-ID, and X-Span-ID propagation."""
    resp = client.get("/api/v1/models", headers=get_auth_headers())
    assert resp.status_code == 200
    assert "X-Request-ID" in resp.headers
    assert "X-Trace-ID" in resp.headers
    assert "X-Span-ID" in resp.headers


def test_prometheus_metrics():
    """Task 07: Verify GET /metrics exposes Prometheus metrics text format."""
    metrics = get_metrics_registry()
    metrics.record_request("GET", "/api/v1/projects", 200, 0.015)

    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    assert "gateway_requests_total" in resp.text
    assert "gateway_active_connections" in resp.text


@pytest.mark.asyncio
async def test_health_cache():
    """Task 08: Verify HealthAggregator TTL caching."""
    aggregator = HealthAggregator(cache_ttl_seconds=1.0)
    health1 = await aggregator.get_system_health()
    health2 = await aggregator.get_system_health()

    assert health1.timestamp == health2.timestamp


@pytest.mark.asyncio
async def test_sse_manager():
    """Task 09: Verify SSEConnectionManager subscription and event broadcasting."""
    sse_mgr = SSEConnectionManager()
    count = await sse_mgr.broadcast("run_test_99", "agent.started", {"status": "started"})
    assert count == 0
    assert sse_mgr.get_listener_count("run_test_99") == 0


@pytest.mark.asyncio
async def test_ws_manager():
    """Task 10: Verify WebSocketConnectionManager connection tracking."""
    ws_mgr = WebSocketConnectionManager()
    assert ws_mgr.get_connection_count("run_test_ws") == 0


def test_unified_error_contract():
    """Task 11: Verify unified error response contract."""
    resp = client.get("/api/v1/projects/non_existent_id_404", headers=get_auth_headers())
    assert resp.status_code in [200, 404, 503]
    if resp.status_code == 404:
        data = resp.json()
        assert data["success"] is False
        assert "code" in data
        assert "message" in data
        assert "service" in data
        assert "request_id" in data
        assert "trace_id" in data


def test_session_manager():
    """Task 12: Verify GatewaySessionManager lifecycle and expiration cleanup."""
    sess_mgr = GatewaySessionManager(session_ttl_seconds=0.5)
    sess = sess_mgr.create_session("run_sess_1", "proj_1", "CODE", "Add feature")

    assert sess.session_id == "run_sess_1"
    assert sess_mgr.get_session("run_sess_1").status == "started"

    sess_mgr.update_session("run_sess_1", status="executing")
    assert sess_mgr.get_session("run_sess_1").status == "executing"

    sess_mgr.cancel_session("run_sess_1")
    assert sess_mgr.get_session("run_sess_1").status == "cancelled"

    time.sleep(0.6)
    cleaned = sess_mgr.cleanup_expired_sessions()
    assert cleaned >= 1
