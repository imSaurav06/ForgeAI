from services.gateway.app.services.proxy_service import GatewayProxyService


def get_proxy_service() -> GatewayProxyService:
    """Dependency providing a GatewayProxyService instance."""
    return GatewayProxyService()
