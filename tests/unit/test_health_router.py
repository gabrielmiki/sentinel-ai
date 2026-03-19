"""
Tests for health router endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient


class TestHealthLiveness:
    """Tests for GET /health endpoint."""

    def test_health_returns_200_ok(self, sync_client: TestClient) -> None:
        """Verify liveness endpoint returns 200 OK."""
        response = sync_client.get("/health")
        assert response.status_code == 200

    def test_health_returns_correct_json_structure(self, sync_client: TestClient) -> None:
        """Verify liveness endpoint returns expected JSON structure."""
        response = sync_client.get("/health")
        data = response.json()

        assert "status" in data
        assert "service" in data
        assert data["status"] == "healthy"
        assert data["service"] == "sentinel-ai"


class TestMetricsEndpoint:
    """Tests for GET /metrics endpoint."""

    def test_metrics_returns_200_ok(self, sync_client: TestClient) -> None:
        """Verify metrics endpoint returns 200 OK."""
        response = sync_client.get("/metrics")
        assert response.status_code == 200

    def test_metrics_returns_prometheus_format(self, sync_client: TestClient) -> None:
        """Verify metrics endpoint returns Prometheus exposition format."""
        response = sync_client.get("/metrics")

        # Check content type
        assert "text/plain" in response.headers["content-type"]

        # Check response is plain text (not JSON)
        content = response.text
        assert isinstance(content, str)
        assert len(content) > 0

    def test_metrics_contains_python_info(self, sync_client: TestClient) -> None:
        """Verify metrics contain standard Python runtime metrics."""
        response = sync_client.get("/metrics")
        content = response.text

        # Prometheus metrics should contain HELP and TYPE comments
        assert "# HELP" in content or "# TYPE" in content

        # Should contain Python GC metrics (standard prometheus_client metrics)
        assert "python_" in content or "process_" in content


@pytest.mark.database
class TestReadinessEndpoint:
    """Tests for GET /health/ready endpoint."""

    @pytest.mark.asyncio
    async def test_readiness_returns_200_when_healthy(self, client: AsyncClient) -> None:
        """Verify readiness endpoint returns 200 when all dependencies are healthy."""
        response = await client.get("/health/ready")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_readiness_returns_correct_structure(self, client: AsyncClient) -> None:
        """Verify readiness endpoint returns expected JSON structure."""
        response = await client.get("/health/ready")
        data = response.json()

        assert "status" in data
        assert "dependencies" in data
        assert isinstance(data["dependencies"], list)
        assert len(data["dependencies"]) > 0

    @pytest.mark.asyncio
    async def test_readiness_checks_all_dependencies(self, client: AsyncClient) -> None:
        """Verify readiness endpoint checks all required dependencies."""
        response = await client.get("/health/ready")
        data = response.json()

        dependency_names = {dep["name"] for dep in data["dependencies"]}

        # Should check these dependencies
        assert "postgresql" in dependency_names
        assert "pgvector" in dependency_names
        assert "redis" in dependency_names
        assert "prometheus" in dependency_names

    @pytest.mark.asyncio
    async def test_readiness_dependency_has_required_fields(self, client: AsyncClient) -> None:
        """Verify each dependency status has required fields."""
        response = await client.get("/health/ready")
        data = response.json()

        for dep in data["dependencies"]:
            assert "name" in dep
            assert "status" in dep
            # latency_ms and error are optional depending on status
            if dep["status"] == "healthy":
                assert "latency_ms" in dep
                assert isinstance(dep["latency_ms"], (int, float))
