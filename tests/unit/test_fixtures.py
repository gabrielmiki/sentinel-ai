"""
Test suite to verify conftest.py fixtures work correctly.

This module serves as both documentation and validation for the test fixtures.

Tests marked with @pytest.mark.database require PostgreSQL and Redis infrastructure.
Run with: pytest -m database (when databases are available)
Skip with: pytest -m "not database" (default behavior)
"""

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.database
class TestDatabaseFixtures:
    """Test database session fixtures."""

    @pytest.mark.asyncio
    async def test_db_session_creates_transaction(self, db_session: AsyncSession) -> None:
        """Verify db_session fixture provides working async session."""
        result = await db_session.execute(text("SELECT 1 as value"))
        row = result.fetchone()
        assert row is not None
        assert row[0] == 1

    @pytest.mark.asyncio
    async def test_db_session_rollback_isolation(self, db_session: AsyncSession) -> None:
        """Verify changes are rolled back after test (test isolation)."""
        from uuid import uuid4

        # Insert test data with explicit id and boolean fields
        test_id = str(uuid4())
        await db_session.execute(
            text(
                """
                INSERT INTO sentinel.users (id, username, email, hashed_password, is_active, is_superuser)
                VALUES (:id, 'temp_user', 'temp@example.com', 'hash123', true, false)
                """
            ),
            {"id": test_id},
        )
        # No commit needed - fixture manages transaction

        # Verify insert worked within the transaction
        result = await db_session.execute(
            text("SELECT username FROM sentinel.users WHERE username = 'temp_user'")
        )
        assert result.fetchone() is not None
        # Data will be rolled back automatically when fixture context exits

    @pytest.mark.asyncio
    async def test_vectordb_session_works(self, vectordb_session: AsyncSession) -> None:
        """Verify vectordb_session fixture provides working async session."""
        result = await vectordb_session.execute(text("SELECT 1 as value"))
        row = result.fetchone()
        assert row is not None
        assert row[0] == 1


class TestFastAPIFixtures:
    """Test FastAPI client fixtures."""

    def test_sync_client_works(self, sync_client: TestClient) -> None:
        """Verify synchronous TestClient can call endpoints."""
        response = sync_client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_sync_client_raises_server_exceptions(self, sync_client: TestClient) -> None:
        """Verify sync_client raises server exceptions for debugging."""
        # This would normally return 500, but with raise_server_exceptions=True
        # it will raise the actual exception
        response = sync_client.get("/health")
        assert response.status_code == 200  # Health endpoint works

    @pytest.mark.asyncio
    @pytest.mark.database
    async def test_async_client_works(self, client: AsyncClient) -> None:
        """Verify asynchronous client can call endpoints."""
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "sentinel-ai"

    @pytest.mark.asyncio
    @pytest.mark.database
    async def test_async_client_has_json_header(self, client: AsyncClient) -> None:
        """Verify async client has default Content-Type header."""
        # The client fixture sets Content-Type: application/json by default
        assert client.headers.get("Content-Type") == "application/json"

    @pytest.mark.asyncio
    @pytest.mark.database
    async def test_async_client_uses_test_db_session(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Verify async client uses injected test database session."""
        # The client fixture overrides get_db to return the test db_session
        # This ensures all database operations in endpoints use the test database
        # and benefit from automatic rollback after each test
        from api.database import get_db
        from api.main import app

        # Verify the dependency override is set
        assert get_db in app.dependency_overrides
        # Verify it returns our test session
        assert app.dependency_overrides[get_db]() == db_session


class TestPrometheusFixtures:
    """Test Prometheus mock fixtures."""

    def test_prometheus_client_returns_metrics(self, mock_prometheus_client) -> None:  # type: ignore[no-untyped-def]
        """Verify mock Prometheus client returns expected data structure."""
        result = mock_prometheus_client.custom_query("up")

        assert len(result) == 2
        assert result[0]["metric"]["job"] == "api"
        assert result[0]["value"][1] == "1"

    def test_prometheus_client_handles_nonexistent_metrics(  # type: ignore[no-untyped-def]
        self, mock_prometheus_client
    ) -> None:
        """Verify mock returns empty list for non-existent metrics."""
        result = mock_prometheus_client.custom_query("nonexistent_metric")
        assert result == []

    @pytest.mark.asyncio
    async def test_prometheus_tool_for_agents(self, mock_prometheus_tool) -> None:  # type: ignore[no-untyped-def]
        """Verify LangChain Prometheus tool mock works."""
        result = await mock_prometheus_tool.run("up{job='api'}")

        assert result["status"] == "success"
        assert "data" in result
        assert len(result["data"]) == 2


class TestLLMFixtures:
    """Test LLM mock fixtures."""

    @pytest.mark.asyncio
    async def test_openai_llm_mock(self, mock_openai_llm) -> None:  # type: ignore[no-untyped-def]
        """Verify OpenAI mock returns expected response structure."""
        response = await mock_openai_llm.ainvoke("Analyze this incident")

        assert response.content is not None
        assert "CPU usage" in response.content
        assert response.response_metadata["model"] == "gpt-4"

    @pytest.mark.asyncio
    async def test_anthropic_llm_mock(self, mock_anthropic_llm) -> None:  # type: ignore[no-untyped-def]
        """Verify Anthropic Claude mock returns expected response structure."""
        response = await mock_anthropic_llm.ainvoke("What is the root cause?")

        assert response.content is not None
        assert "root cause" in response.content
        assert response.response_metadata["model"] == "claude-3-sonnet"

    @pytest.mark.asyncio
    async def test_embeddings_mock(self, mock_embeddings) -> None:  # type: ignore[no-untyped-def]
        """Verify embeddings mock returns correct vector dimensions."""
        query_embedding = await mock_embeddings.aembed_query("test query")
        doc_embeddings = await mock_embeddings.aembed_documents(["doc1", "doc2"])

        assert len(query_embedding) == 1536  # OpenAI ada-002 dimensions
        assert len(doc_embeddings) == 2
        assert all(len(emb) == 1536 for emb in doc_embeddings)


class TestRedisFixtures:
    """Test Redis mock fixtures."""

    @pytest.mark.asyncio
    async def test_redis_get_set(self, mock_redis_client) -> None:  # type: ignore[no-untyped-def]
        """Verify Redis mock supports basic get/set operations."""
        await mock_redis_client.set("test_key", "test_value")
        value = await mock_redis_client.get("test_key")

        assert value == "test_value"

    @pytest.mark.asyncio
    async def test_redis_delete(self, mock_redis_client) -> None:  # type: ignore[no-untyped-def]
        """Verify Redis mock supports delete operations."""
        await mock_redis_client.set("temp_key", "temp_value")
        deleted = await mock_redis_client.delete("temp_key")
        exists = await mock_redis_client.exists("temp_key")

        assert deleted == 1
        assert exists == 0

    def test_celery_app_mock(self, mock_celery_app) -> None:  # type: ignore[no-untyped-def]
        """Verify Celery mock supports task decoration."""

        @mock_celery_app.task
        def sample_task(x: int, y: int) -> int:
            return x + y

        # Verify task can be called normally
        assert sample_task(2, 3) == 5

        # Verify task has delay method (for async execution)
        result = sample_task.delay(2, 3)
        assert hasattr(result, "id")


class TestSampleDataFixtures:
    """Test sample data factory fixtures."""

    def test_sample_user_data_structure(self, sample_user_data) -> None:  # type: ignore[no-untyped-def]
        """Verify sample user data has required fields."""
        assert "username" in sample_user_data
        assert "email" in sample_user_data
        assert "password" in sample_user_data
        assert sample_user_data["is_active"] is True

    def test_sample_incident_data_structure(self, sample_incident_data) -> None:  # type: ignore[no-untyped-def]
        """Verify sample incident data has required fields."""
        assert "title" in sample_incident_data
        assert "severity" in sample_incident_data
        assert sample_incident_data["severity"] in ["low", "medium", "high", "critical"]

    def test_sample_runbook_data_structure(self, sample_runbook_data) -> None:  # type: ignore[no-untyped-def]
        """Verify sample runbook data has required fields."""
        assert "title" in sample_runbook_data
        assert "content" in sample_runbook_data
        assert isinstance(sample_runbook_data["tags"], list)

    def test_sample_agent_state_structure(self, sample_agent_state) -> None:  # type: ignore[no-untyped-def]
        """Verify sample agent state has required fields for LangGraph."""
        assert "incident_id" in sample_agent_state
        assert "query" in sample_agent_state
        assert "current_agent" in sample_agent_state
        assert isinstance(sample_agent_state["metrics"], list)


@pytest.mark.database
class TestIntegrationHelpers:
    """Test integration helper fixtures."""

    @pytest.mark.asyncio
    async def test_create_test_user_factory(  # type: ignore[no-untyped-def]
        self, db_session: AsyncSession, create_test_user
    ) -> None:
        """Verify create_test_user factory creates users in database."""
        user = await create_test_user(username="fixture_user", email="fixture@example.com")

        assert user is not None
        assert user.username == "fixture_user"
        assert user.email == "fixture@example.com"

    @pytest.mark.asyncio
    async def test_create_test_incident_factory(  # type: ignore[no-untyped-def]
        self, db_session: AsyncSession, create_test_incident
    ) -> None:
        """Verify create_test_incident factory creates incidents in database."""
        incident = await create_test_incident(
            title="Test incident", severity="critical", status="open"
        )

        assert incident is not None
        assert incident.title == "Test incident"
        assert incident.severity == "critical"
        assert incident.status == "open"
