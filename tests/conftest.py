from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from shared.utils.app_factory import create_app


@pytest.fixture
def sample_app():
    """Fixture providing a standard test application instance."""
    app = create_app(
        service_name="test-service",
        service_version="0.1.0",
        description="Test microservice instance for foundation testing.",
    )
    return app


@pytest.fixture
def client(sample_app) -> Generator[TestClient, None, None]:
    """Fixture providing a FastAPI TestClient for the sample app."""
    with TestClient(sample_app) as test_client:
        yield test_client
