import time
from typing import Any

import httpx
from fastapi import Request, Response

from services.gateway.app.core.circuit_breaker import get_circuit_breaker_registry
from services.gateway.app.core.config import get_gateway_settings
from services.gateway.app.core.internal_auth import InternalAuthManager
from services.gateway.app.core.metrics import get_metrics_registry
from services.gateway.app.core.retry import RetryPolicy
from services.gateway.app.core.service_registry import get_service_registry
from shared.exceptions.handlers import ServiceUnavailableException
from shared.logging.logger import get_request_id, get_span_id, get_trace_id, logger


class HttpProxyClient:
    """Production-grade HTTP proxy client with circuit breakers, retries, internal auth, and metrics."""

    def __init__(self, timeout: float | None = None) -> None:
        settings = get_gateway_settings()
        self.timeout = timeout if timeout is not None else settings.proxy_timeout_seconds
        self.registry = get_service_registry()
        self.breaker_registry = get_circuit_breaker_registry()
        self.auth_manager = InternalAuthManager()
        self.metrics = get_metrics_registry()
        self.retry_policy = RetryPolicy(max_retries=3, initial_delay=0.1)

    async def forward_request(
        self,
        service_name: str,
        path: str,
        request: Request,
        json_body: Any | None = None,
        params: dict[str, Any] | None = None,
        user_id: str | None = None,
        user_role: str | None = None,
        method: str | None = None,
    ) -> Response:
        """
        Forward request to registered downstream service with circuit breaker, retries, and auth.
        """
        service_key = service_name.lower()
        target_base_url = self.registry.get_service_url(service_key)
        target_url = f"{target_base_url.rstrip('/')}/{path.lstrip('/')}"
        effective_method = method or request.method
        logger.info(f"PROXYING {effective_method} {request.url.path} -> {target_url}")

        # Step 1: Verify Circuit Breaker State
        self.breaker_registry.verify_request_allowed(service_key)

        req_id = get_request_id()
        trc_id = get_trace_id()
        spn_id = get_span_id()

        # Step 2: Prepare Headers — Strip any client-controlled identity or internal headers
        headers = {
            key: value
            for key, value in request.headers.items()
            if key.lower() not in ("host", "content-length", "x-user-id", "x-user-role", "x-internal-service-token")
        }
        headers["X-Request-ID"] = req_id
        headers["X-Trace-ID"] = trc_id
        headers["X-Span-ID"] = spn_id

        # Use verified identity passed from gateway auth dependency or request state
        auth_context = getattr(request.state, "auth_context", None)
        effective_user_id = user_id or (auth_context.get("user_id") if isinstance(auth_context, dict) else None) or "user_dev_local"
        effective_user_role = user_role or (auth_context.get("role") if isinstance(auth_context, dict) else None) or "user"

        self.auth_manager.inject_internal_headers(headers, user_id=effective_user_id, user_role=effective_user_role)

        query_params = params if params is not None else dict(request.query_params)
        start_time = time.perf_counter()

        # Helper function for execution inside retry loop
        async def _make_request() -> Response:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                response = await client.request(
                    method=effective_method,
                    url=target_url,
                    headers=headers,
                    params=query_params,
                    json=json_body,
                )

                if response.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        message=f"Downstream service error {response.status_code}",
                        request=response.request,
                        response=response,
                    )

                resp_headers = {
                    key: value
                    for key, value in response.headers.items()
                    if key.lower() not in ("content-encoding", "content-length", "transfer-encoding")
                }
                return Response(
                    content=response.content,
                    status_code=response.status_code,
                    headers=resp_headers,
                    media_type=response.headers.get("content-type", "application/json"),
                )

        def _is_retryable_exception(exc: Exception) -> bool:
            if isinstance(exc, (httpx.ConnectError, httpx.TimeoutException)):
                return True
            if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in {502, 503, 504}:
                return True
            return False

        breaker = self.breaker_registry.get_breaker(service_key)

        try:
            res = await self.retry_policy.execute(
                func=_make_request,
                is_retryable_exception=_is_retryable_exception,
                method=request.method,
            )
            duration_sec = time.perf_counter() - start_time
            breaker.record_success()
            self.registry.set_service_status(service_key, "healthy")
            self.metrics.record_request(request.method, request.url.path, res.status_code, duration_sec)
            return res

        except Exception as err:
            duration_sec = time.perf_counter() - start_time
            breaker.record_failure()
            self.registry.set_service_status(service_key, "degraded" if breaker.state != "OPEN" else "offline")
            self.metrics.record_downstream_failure(service_key)
            self.metrics.record_request(request.method, request.url.path, 503, duration_sec)

            logger.error(f"Downstream service call to '{service_key}' at {target_url} failed: {err}")
            raise ServiceUnavailableException(
                message=f"Downstream microservice '{service_key}' is unavailable",
                details={"service": service_key, "target_url": target_url, "error": str(err)},
            ) from err
