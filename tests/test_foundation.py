from fastapi.testclient import TestClient

from shared.config.settings import get_settings
from shared.exceptions.handlers import NotFoundException
from shared.logging.logger import setup_logger
from shared.schemas.responses import HealthResponse
from shared.utils.app_factory import create_app


def test_settings_load():
    """Verify settings initialization and defaults."""
    settings = get_settings()
    assert settings.environment in ["development", "testing", "production"]
    assert settings.log_level is not None
    assert settings.gateway_port == 8000
    assert settings.agent_service_port == 8001
    assert settings.llm_service_port == 8002
    assert settings.repository_service_port == 8003
    assert settings.retrieval_service_port == 8004
    assert settings.tool_service_port == 8005
    assert settings.git_service_port == 8006
    assert settings.evaluation_service_port == 8007


def test_health_endpoint(client: TestClient):
    """Verify /health endpoint returns HTTP 200 and HealthResponse format."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()

    health_model = HealthResponse(**data)
    assert health_model.service == "test-service"
    assert health_model.status == "healthy"
    assert health_model.version == "0.1.0"


def test_request_id_middleware(client: TestClient):
    """Verify request ID is generated and returned in headers."""
    response = client.get("/health")
    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    assert len(response.headers["X-Request-ID"]) > 0

    # Custom request ID header passing
    custom_id = "custom-test-trace-12345"
    response_custom = client.get("/health", headers={"X-Request-ID": custom_id})
    assert response_custom.headers["X-Request-ID"] == custom_id


def test_swagger_openapi_docs(client: TestClient):
    """Verify /docs and /openapi.json are accessible."""
    docs_resp = client.get("/docs")
    assert docs_resp.status_code == 200

    openapi_resp = client.get("/openapi.json")
    assert openapi_resp.status_code == 200
    openapi_data = openapi_resp.json()
    assert "paths" in openapi_data
    assert "/health" in openapi_data["paths"]


def test_custom_exception_handling():
    """Verify custom exception converts to ErrorResponse structure."""
    app = create_app(service_name="exception-test-service")

    @app.get("/trigger-error")
    def trigger_error():
        raise NotFoundException("User resource missing")

    test_client = TestClient(app)
    response = test_client.get("/trigger-error")
    assert response.status_code == 404
    data = response.json()
    assert data["success"] is False
    assert data["message"] == "User resource missing"
    assert data["error"]["code"] == "NOT_FOUND"


def test_structured_logger():
    """Verify loguru setup initialization."""
    bound_logger = setup_logger("test-service", "DEBUG")
    assert bound_logger is not None
    bound_logger.info("Test log entry")


def test_all_services_instantiation():
    """Verify all 8 service main modules instantiate app factory cleanly."""
    from services.agent.main import app as agent_app
    from services.evaluation.main import app as eval_app
    from services.gateway.main import app as gateway_app
    from services.git.main import app as git_app
    from services.llm.main import app as llm_app
    from services.repository.main import app as repo_app
    from services.retrieval.main import app as retrieval_app
    from services.tools.main import app as tools_app

    apps = [
        gateway_app,
        agent_app,
        llm_app,
        repo_app,
        retrieval_app,
        tools_app,
        git_app,
        eval_app,
    ]

    for app_instance in apps:
        tc = TestClient(app_instance)
        res = tc.get("/health")
        assert res.status_code == 200
        assert res.json()["status"] == "healthy"
