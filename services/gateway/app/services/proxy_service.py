from typing import Any

from fastapi import Request, Response

from services.gateway.app.core.proxy import HttpProxyClient


class GatewayProxyService:
    """Service mapping target microservice requests through HttpProxyClient."""

    def __init__(self, proxy_client: HttpProxyClient | None = None) -> None:
        self.proxy_client = proxy_client or HttpProxyClient()

    async def proxy_to_service(
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
        """Forward request to named downstream microservice."""
        return await self.proxy_client.forward_request(
            service_name=service_name,
            path=path,
            request=request,
            json_body=json_body,
            params=params,
            user_id=user_id,
            user_role=user_role,
            method=method,
        )
