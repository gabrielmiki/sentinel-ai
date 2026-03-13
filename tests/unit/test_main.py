"""
Tests for FastAPI application endpoints (api/main.py).
"""

from fastapi.testclient import TestClient


class TestHealthEndpoint:
    """Test health check endpoint."""

    def test_health_returns_200(self, sync_client: TestClient) -> None:
        """Verify health endpoint returns 200 OK."""
        response = sync_client.get("/health")
        assert response.status_code == 200

    def test_health_returns_correct_data(self, sync_client: TestClient) -> None:
        """Verify health endpoint returns expected JSON structure."""
        response = sync_client.get("/health")
        data = response.json()

        assert data["status"] == "healthy"
        assert data["service"] == "sentinel-ai"


class TestRootEndpoint:
    """Test root endpoint."""

    def test_root_returns_200(self, sync_client: TestClient) -> None:
        """Verify root endpoint returns 200 OK."""
        response = sync_client.get("/")
        assert response.status_code == 200

    def test_root_returns_correct_data(self, sync_client: TestClient) -> None:
        """Verify root endpoint returns expected JSON structure."""
        response = sync_client.get("/")
        data = response.json()

        assert data["message"] == "SentinelAI API"
        assert data["version"] == "0.1.0"
        assert data["status"] == "running"
