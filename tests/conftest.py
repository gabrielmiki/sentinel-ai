"""
Pytest configuration and shared fixtures for SentinelAI test suite.

Provides fixtures for:
- Test databases (PostgreSQL + pgvector)
- FastAPI TestClient
- Mocked external services (Prometheus, LLMs, Redis)
- Sample data factories
"""

import asyncio
import os
from collections.abc import AsyncGenerator, Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

# Environment variables for test databases
TEST_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://sentinel:sentinel@localhost:5432/sentinel_test",
)
TEST_VECTORDB_URL = os.getenv(
    "VECTORDB_URL",
    "postgresql+asyncpg://vectoradmin:vectorpass@localhost:5433/vectordb_test",
)
TEST_REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


# ==================== Event Loop Fixture ====================


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """
    Session-scoped event loop for session-scoped async fixtures.

    Required to prevent "got Future attached to a different loop" errors
    when using session-scoped async fixtures (db_engine, vectordb_engine).
    """
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


# ==================== Database Fixtures ====================


@pytest_asyncio.fixture(scope="session")
async def db_engine() -> AsyncGenerator[AsyncEngine, None]:
    """
    Create async engine for test database (application data).

    Scope: session - reuse engine across all tests for performance.

    Raises:
        RuntimeError: If database extensions or schema creation fails
            (e.g., missing superuser privileges, unavailable extensions)
    """
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )

    # Initialize schema with explicit error handling
    try:
        async with engine.begin() as conn:
            # Create required PostgreSQL extensions
            await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"'))
            await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "pg_trgm"'))

            # Create schema
            await conn.execute(text("CREATE SCHEMA IF NOT EXISTS sentinel"))

            # Import all models to ensure they're registered with Base.metadata
            from api.models import AgentRun, Base, Incident, Runbook, User  # noqa: F401

            # Create all tables from ORM model definitions
            await conn.run_sync(Base.metadata.create_all)
    except Exception as e:
        await engine.dispose()
        raise RuntimeError(
            f"Failed to initialize test database schema and tables. "
            f"Ensure PostgreSQL extensions (uuid-ossp, pg_trgm) are available "
            f"and user has CREATE EXTENSION privileges. "
            f"Original error: {e}"
        ) from e

    yield engine

    # Cleanup
    await engine.dispose()


@pytest_asyncio.fixture(scope="session")
async def vectordb_engine() -> AsyncGenerator[AsyncEngine, None]:
    """
    Create async engine for vector database (embeddings).

    Scope: session - reuse engine across all tests for performance.

    Raises:
        RuntimeError: If pgvector extension or schema creation fails
            (e.g., missing pgvector installation, insufficient privileges)
    """
    engine = create_async_engine(
        TEST_VECTORDB_URL,
        echo=False,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )

    # Initialize schema with explicit error handling
    try:
        async with engine.begin() as conn:
            # Create pgvector extension
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

            # Create schema
            await conn.execute(text("CREATE SCHEMA IF NOT EXISTS embeddings"))

            # Import all vector models to ensure they're registered with VectorBase.metadata
            from api.models import (  # noqa: F401
                IncidentEmbedding,
                RunbookEmbedding,
                VectorBase,
            )

            # Create all tables from ORM model definitions
            await conn.run_sync(VectorBase.metadata.create_all)
    except Exception as e:
        await engine.dispose()
        raise RuntimeError(
            f"Failed to initialize vector database schema and tables. "
            f"Ensure pgvector extension is installed (apt-get install postgresql-16-pgvector) "
            f"and user has CREATE EXTENSION privileges. "
            f"Original error: {e}"
        ) from e

    yield engine

    # Cleanup
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """
    Create a new database session for each test with automatic rollback.

    Ensures test isolation by rolling back all changes after each test.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker

    async_session_maker = async_sessionmaker(
        db_engine,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async with async_session_maker() as session:  # noqa: SIM117
        async with session.begin():
            yield session
            # Transaction is automatically rolled back on exit (not committed)


@pytest_asyncio.fixture
async def vectordb_session(
    vectordb_engine: AsyncEngine,
) -> AsyncGenerator[AsyncSession, None]:
    """
    Create a new vector database session for each test with automatic rollback.

    Ensures test isolation for embedding operations.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker

    async_session_maker = async_sessionmaker(
        vectordb_engine,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async with async_session_maker() as session:  # noqa: SIM117
        async with session.begin():
            yield session
            # Transaction is automatically rolled back on exit (not committed)


# ==================== FastAPI TestClient Fixtures ====================


@pytest.fixture
def sync_client() -> Generator[TestClient, None, None]:
    """
    Synchronous TestClient for FastAPI application.

    Use for simple non-async endpoint testing. Server exceptions are raised
    directly for easier debugging.

    Note: Does not support database dependency injection. Use `client` fixture
    for endpoints that require database access.
    """
    # Import inside fixture to avoid circular imports at module load time
    from api.main import app

    with TestClient(app, raise_server_exceptions=True) as test_client:
        yield test_client


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    Asynchronous HTTP client for FastAPI application with test database injection.

    Features:
    - ASGITransport for proper async endpoint support
    - Automatic database session override (uses test db_session)
    - Default Content-Type: application/json header
    - Guaranteed cleanup via dependency_overrides.clear()

    Use for testing async endpoints, SSE streams, database operations, and WebSockets.

    Example:
        async def test_create_user(client: AsyncClient):
            response = await client.post("/api/users", json={"username": "test"})
            assert response.status_code == 201

    Raises:
        ImportError: If circular imports prevent loading api.database or api.main
    """
    # Import inside fixture to avoid circular imports at module load time
    try:
        from httpx import ASGITransport

        from api.database import get_db
        from api.main import app
    except ImportError as e:
        raise ImportError(
            f"Failed to import FastAPI app or database dependencies. "
            f"This may indicate a circular import issue. "
            f"Check that api.database and api.main do not import test modules. "
            f"Original error: {e}"
        ) from e

    # Override database dependency to use test session
    app.dependency_overrides[get_db] = lambda: db_session

    try:
        # Create async client with ASGI transport for proper async support
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Content-Type": "application/json"},
        ) as async_client:
            yield async_client
    finally:
        # Clear overrides outside async context to guarantee cleanup even on failure
        app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def vectordb_client(
    vectordb_session: AsyncSession,
) -> AsyncGenerator[AsyncClient, None]:
    """
    Asynchronous HTTP client for testing vector database operations.

    Similar to `client` fixture but overrides `get_vectordb` instead of `get_db`.
    Use for testing endpoints that perform RAG searches or embedding operations.

    Example:
        async def test_search_runbooks(vectordb_client: AsyncClient):
            response = await vectordb_client.post(
                "/api/embeddings/search",
                json={"query": "database connection error"}
            )
            assert response.status_code == 200

    Raises:
        ImportError: If circular imports prevent loading api.database or api.main
    """
    # Import inside fixture to avoid circular imports at module load time
    try:
        from httpx import ASGITransport

        from api.database import get_vectordb
        from api.main import app
    except ImportError as e:
        raise ImportError(
            f"Failed to import FastAPI app or database dependencies. "
            f"This may indicate a circular import issue. "
            f"Check that api.database and api.main do not import test modules. "
            f"Original error: {e}"
        ) from e

    # Override vector database dependency to use test session
    app.dependency_overrides[get_vectordb] = lambda: vectordb_session

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Content-Type": "application/json"},
        ) as async_client:
            yield async_client
    finally:
        app.dependency_overrides.clear()


# ==================== Prometheus Mock Fixtures ====================


@pytest.fixture
def mock_prometheus_client() -> Mock:
    """
    Mock Prometheus API client for testing metric queries.

    Returns pre-configured mock responses for common PromQL queries.
    """
    mock_client = Mock()

    # Mock successful metric query response
    mock_client.custom_query.return_value = [
        {
            "metric": {"__name__": "up", "job": "api", "instance": "backend-1:8000"},
            "value": [1678886400, "1"],
        },
        {
            "metric": {"__name__": "up", "job": "api", "instance": "backend-2:8000"},
            "value": [1678886400, "1"],
        },
    ]

    # Mock range query response
    mock_client.custom_query_range.return_value = [
        {
            "metric": {"__name__": "cpu_usage", "instance": "backend-1:8000"},
            "values": [
                [1678886400, "45.2"],
                [1678886460, "47.8"],
                [1678886520, "43.1"],
            ],
        }
    ]

    # Mock empty response for non-existent metrics
    mock_client.custom_query.side_effect = lambda query: (
        [] if "nonexistent" in query else mock_client.custom_query.return_value
    )

    return mock_client


@pytest.fixture
def mock_prometheus_tool(mock_prometheus_client: Mock) -> Mock:
    """
    Mock LangChain Prometheus tool for agent testing.

    Returns mock tool that agents can call during graph execution.
    """
    mock_tool = Mock()
    mock_tool.name = "prometheus_query"
    mock_tool.description = "Query Prometheus metrics using PromQL"
    mock_tool.run = AsyncMock(
        return_value={
            "status": "success",
            "data": mock_prometheus_client.custom_query.return_value,
        }
    )
    return mock_tool


# ==================== LLM Mock Fixtures ====================


@pytest.fixture
def mock_openai_llm() -> AsyncMock:
    """
    Mock OpenAI LLM for testing LangChain/LangGraph agents.

    Returns pre-configured responses for common prompts.
    """
    mock_llm = AsyncMock()

    # Mock standard completion response
    mock_llm.ainvoke.return_value = MagicMock(
        content=(
            "Based on the Prometheus metrics, I detected high CPU usage "
            "(>80%) on backend-1 at 14:30 UTC. This correlates with the "
            "increased error rate observed in the logs."
        ),
        response_metadata={"model": "gpt-4", "usage": {"total_tokens": 125}},
    )

    # Mock streaming response
    async def mock_astream(prompt: str) -> AsyncGenerator[str, None]:
        chunks = ["Based ", "on the ", "metrics, ", "high CPU ", "detected."]
        for chunk in chunks:
            yield MagicMock(content=chunk)

    mock_llm.astream.return_value = mock_astream("")

    return mock_llm


@pytest.fixture
def mock_anthropic_llm() -> AsyncMock:
    """
    Mock Anthropic Claude LLM for testing LangChain/LangGraph agents.

    Returns pre-configured responses for common prompts.
    """
    mock_llm = AsyncMock()

    mock_llm.ainvoke.return_value = MagicMock(
        content=(
            "I've analyzed the incident data. The root cause appears to be "
            "database connection pool exhaustion during peak traffic hours."
        ),
        response_metadata={"model": "claude-3-sonnet", "usage": {"input_tokens": 450}},
    )

    return mock_llm


@pytest.fixture
def mock_embeddings() -> AsyncMock:
    """
    Mock OpenAI embeddings for testing RAG and vector search.

    Returns deterministic embedding vectors for reproducible tests.
    """
    mock_embeddings = AsyncMock()

    # Return consistent 1536-dimensional embeddings (OpenAI ada-002 format)
    mock_embeddings.aembed_query.return_value = [0.1] * 1536
    mock_embeddings.aembed_documents.return_value = [[0.1] * 1536, [0.2] * 1536]

    return mock_embeddings


# ==================== Redis Mock Fixtures ====================


@pytest.fixture
def mock_redis_client() -> AsyncMock:
    """
    Mock Redis client for testing session storage and caching.

    Simulates in-memory key-value store without actual Redis connection.
    """
    mock_redis = AsyncMock()

    # In-memory storage for testing
    _storage: dict[str, Any] = {}

    # Mock get/set operations
    async def mock_get(key: str) -> str | None:
        return _storage.get(key)

    async def mock_set(key: str, value: str, ex: int | None = None) -> bool:
        _storage[key] = value
        return True

    async def mock_delete(key: str) -> int:
        if key in _storage:
            del _storage[key]
            return 1
        return 0

    async def mock_exists(key: str) -> int:
        return 1 if key in _storage else 0

    mock_redis.get.side_effect = mock_get
    mock_redis.set.side_effect = mock_set
    mock_redis.delete.side_effect = mock_delete
    mock_redis.exists.side_effect = mock_exists

    # Mock pipeline operations
    mock_pipeline = AsyncMock()
    mock_pipeline.execute.return_value = [True, True]
    mock_redis.pipeline.return_value = mock_pipeline

    return mock_redis


@pytest.fixture
def mock_celery_app() -> Mock:
    """
    Mock Celery application for testing async task execution.

    Allows testing task logic without actual Celery worker.
    """
    mock_app = Mock()

    # Mock task decorator
    def mock_task(func: Any) -> Any:
        func.delay = Mock(return_value=Mock(id=str(uuid4())))
        func.apply_async = Mock(return_value=Mock(id=str(uuid4())))
        return func

    mock_app.task = mock_task

    return mock_app


# ==================== Sample Data Factories ====================


@pytest.fixture
def sample_user_data() -> dict[str, Any]:
    """Sample user data for testing user-related endpoints."""
    return {
        "username": "testuser",
        "email": "test@example.com",
        "password": "SecurePass123!",
        "is_active": True,
        "is_superuser": False,
    }


@pytest.fixture
def sample_incident_data() -> dict[str, Any]:
    """Sample incident data for testing incident creation and updates."""
    return {
        "title": "High CPU usage on backend-1",
        "description": "CPU usage exceeded 90% for 10 minutes",
        "severity": "critical",
        "status": "open",
    }


@pytest.fixture
def sample_runbook_data() -> dict[str, Any]:
    """Sample runbook data for testing RAG retrieval."""
    return {
        "title": "How to handle high CPU usage",
        "content": (
            "1. Check top processes with 'top' command\n"
            "2. Identify resource-intensive processes\n"
            "3. Consider horizontal scaling\n"
            "4. Review recent deployments"
        ),
        "tags": ["cpu", "performance", "troubleshooting"],
        "category": "infrastructure",
    }


@pytest.fixture
def sample_agent_state() -> dict[str, Any]:
    """Sample LangGraph agent state for testing graph execution."""
    return {
        "incident_id": str(uuid4()),
        "query": "Investigate high error rate in production",
        "metrics": [],
        "runbooks": [],
        "analysis": "",
        "recommendations": [],
        "current_agent": "supervisor",
    }


# ==================== Integration Test Helpers ====================


@pytest.fixture
def create_test_user(db_session: AsyncSession) -> Any:
    """
    Factory fixture for creating test users in the database.

    Usage:
        user = await create_test_user(username="testuser")

    Raises:
        RuntimeError: If user creation fails due to FK violations, unique constraints,
            schema mismatches, or missing columns. Includes the attempted data for debugging.
    """

    async def _create_user(**kwargs: Any) -> Any:
        from passlib.context import CryptContext

        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

        # Get password and ensure it's within bcrypt's 72-byte limit
        password = kwargs.get("password", "testpass123")
        password_bytes = password.encode("utf-8")
        if len(password_bytes) > 72:
            # Truncate at byte level, not character level
            password = password_bytes[:72].decode("utf-8", errors="ignore")

        user_data = {
            "id": str(uuid4()),
            "username": kwargs.get("username", f"user_{uuid4().hex[:8]}"),
            "email": kwargs.get("email", f"user_{uuid4().hex[:8]}@example.com"),
            "hashed_password": pwd_context.hash(password),
            "is_active": kwargs.get("is_active", True),
            "is_superuser": kwargs.get("is_superuser", False),
        }

        query = text(
            """
            INSERT INTO sentinel.users (id, username, email, hashed_password, is_active, is_superuser)
            VALUES (:id, :username, :email, :hashed_password, :is_active, :is_superuser)
            RETURNING id, username, email, is_active, is_superuser
            """
        )

        try:
            result = await db_session.execute(query, user_data)
            # No commit needed - fixture manages transaction lifecycle
            return result.fetchone()
        except Exception as e:
            raise RuntimeError(
                f"Failed to create test user. Check for schema mismatches, "
                f"unique constraint violations, or missing sentinel.users table. "
                f"Attempted data: {user_data}. "
                f"Original error: {e}"
            ) from e

    return _create_user


@pytest.fixture
def create_test_incident(db_session: AsyncSession) -> Any:
    """
    Factory fixture for creating test incidents in the database.

    Usage:
        incident = await create_test_incident(title="Test incident", severity="high")

    Raises:
        RuntimeError: If incident creation fails due to FK violations (invalid created_by),
            schema mismatches, or missing columns. Includes the attempted data for debugging.
    """

    async def _create_incident(**kwargs: Any) -> Any:
        incident_data = {
            "id": str(uuid4()),
            "title": kwargs.get("title", "Test incident"),
            "description": kwargs.get("description", "Test description"),
            "severity": kwargs.get("severity", "medium"),
            "status": kwargs.get("status", "open"),
            "created_by": kwargs.get("created_by"),
        }

        query = text(
            """
            INSERT INTO sentinel.incidents (id, title, description, severity, status, created_by)
            VALUES (:id, :title, :description, :severity, :status, :created_by)
            RETURNING id, title, description, severity, status
            """
        )

        try:
            result = await db_session.execute(query, incident_data)
            # No commit needed - fixture manages transaction lifecycle
            return result.fetchone()
        except Exception as e:
            raise RuntimeError(
                f"Failed to create test incident. Check for FK violations (created_by must "
                f"reference existing user), schema mismatches, or missing sentinel.incidents table. "
                f"Attempted data: {incident_data}. "
                f"Original error: {e}"
            ) from e

    return _create_incident
