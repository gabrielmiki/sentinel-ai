"""
Tests for FastAPI application endpoints (api/main.py).
"""

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient


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


class TestApplicationLifespan:
    """Test application lifespan events (startup/shutdown)."""

    @pytest.mark.asyncio
    async def test_lifespan_startup_and_shutdown(self) -> None:
        """Verify lifespan context manager executes startup and shutdown correctly."""
        from api.main import app

        # Create client which triggers lifespan startup
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # App should be running, test a simple endpoint
            response = await client.get("/health")
            assert response.status_code == 200
        # Lifespan shutdown should execute when client closes
