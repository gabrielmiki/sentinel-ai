# SentinelAI Test Suite

Comprehensive test fixtures and utilities for testing the SentinelAI monitoring system.

## Quick Start

```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=api --cov=ingestion --cov-report=html

# Run specific test file
pytest tests/unit/test_fixtures.py

# Run tests matching pattern
pytest -k "test_database"
```

## Database Dependencies

The `api/database.py` module provides FastAPI dependency functions for database access:

- `get_db()` - Yields AsyncSession for application database (PostgreSQL)
- `get_vectordb()` - Yields AsyncSession for vector database (pgvector)

In production, these connect to the real databases. In tests, the `client` fixture automatically overrides `get_db` to use the test database with automatic rollback.

```python
# In your routers
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from api.database import get_db

@router.post("/users")
async def create_user(user: UserCreate, db: AsyncSession = Depends(get_db)):
    # In production: uses real database
    # In tests: uses test database with automatic rollback
    ...
```

## Available Fixtures

### Database Fixtures

#### `db_session` (AsyncSession)
Async SQLAlchemy session for application database. **Automatically rolls back** changes after each test for isolation.

```python
async def test_create_user(db_session: AsyncSession):
    await db_session.execute(
        text("INSERT INTO sentinel.users (username, email, hashed_password) VALUES (...)")
    )
    # Changes automatically rolled back after test
```

#### `vectordb_session` (AsyncSession)
Async SQLAlchemy session for pgvector database. Use for testing embeddings and RAG functionality.

```python
async def test_vector_search(vectordb_session: AsyncSession):
    # Insert test embeddings
    await vectordb_session.execute(
        text("INSERT INTO embeddings.runbook_embeddings (content, embedding) VALUES (...)")
    )
```

### FastAPI Client Fixtures

#### `sync_client` (TestClient)
Synchronous TestClient for simple endpoint testing without database access.

**Features:**
- `raise_server_exceptions=True` - Exceptions are raised directly for easier debugging
- No database dependency injection
- Use only for endpoints that don't require database access

```python
def test_health_endpoint(sync_client: TestClient):
    response = sync_client.get("/health")
    assert response.status_code == 200
```

#### `client` (AsyncClient)
Asynchronous HTTP client with **automatic test database injection**.

**Features:**
- ASGITransport for proper async endpoint support
- Automatic `get_db` dependency override (uses test `db_session`)
- Default `Content-Type: application/json` header
- Guaranteed cleanup via `app.dependency_overrides.clear()`
- Supports SSE streams, WebSockets, and async operations

**Use this for all endpoints that access the database.**

```python
async def test_create_user(client: AsyncClient):
    response = await client.post(
        "/api/users",
        json={"username": "testuser", "email": "test@example.com"}
    )
    assert response.status_code == 201
    # Database changes are automatically rolled back after test
```

```python
async def test_sse_stream(client: AsyncClient):
    async with client.stream("GET", "/api/incidents/stream") as response:
        async for line in response.aiter_lines():
            assert "data:" in line
```

### Prometheus Mock Fixtures

#### `mock_prometheus_client`
Mock Prometheus API client with pre-configured responses.

```python
def test_query_metrics(mock_prometheus_client):
    result = mock_prometheus_client.custom_query("up{job='api'}")
    assert len(result) == 2
    assert result[0]["value"][1] == "1"
```

#### `mock_prometheus_tool`
Mock LangChain tool for testing agent interactions with Prometheus.

```python
async def test_agent_queries_prometheus(mock_prometheus_tool):
    result = await mock_prometheus_tool.run("cpu_usage > 80")
    assert result["status"] == "success"
```

### LLM Mock Fixtures

#### `mock_openai_llm`
Mock OpenAI LLM for testing LangChain/LangGraph agents.

```python
async def test_agent_analysis(mock_openai_llm):
    response = await mock_openai_llm.ainvoke("Analyze incident")
    assert "CPU usage" in response.content
```

#### `mock_anthropic_llm`
Mock Anthropic Claude LLM with different response patterns.

```python
async def test_root_cause_analysis(mock_anthropic_llm):
    response = await mock_anthropic_llm.ainvoke("Find root cause")
    assert "root cause" in response.content
```

#### `mock_embeddings`
Mock OpenAI embeddings for testing RAG retrieval (1536 dimensions).

```python
async def test_similarity_search(mock_embeddings):
    embedding = await mock_embeddings.aembed_query("database error")
    assert len(embedding) == 1536
```

### Redis Mock Fixtures

#### `mock_redis_client`
Mock Redis client with in-memory storage for session/cache testing.

```python
async def test_session_storage(mock_redis_client):
    await mock_redis_client.set("session:123", "user_data", ex=3600)
    value = await mock_redis_client.get("session:123")
    assert value == "user_data"
```

#### `mock_celery_app`
Mock Celery application for testing async task execution.

```python
def test_celery_task(mock_celery_app):
    @mock_celery_app.task
    def analyze_incident(incident_id):
        return {"status": "completed"}

    result = analyze_incident.delay("incident-123")
    assert result.id is not None
```

### Sample Data Fixtures

Pre-configured test data for common entities:

- `sample_user_data` - User registration/authentication data
- `sample_incident_data` - Incident creation data
- `sample_runbook_data` - Runbook with tags and content
- `sample_agent_state` - LangGraph agent state dictionary

```python
def test_create_incident(sample_incident_data):
    assert sample_incident_data["severity"] in ["low", "medium", "high", "critical"]
    assert sample_incident_data["status"] == "open"
```

### Integration Helper Fixtures

#### `create_test_user`
Factory fixture for creating users in test database.

```python
async def test_user_permissions(db_session, create_test_user):
    admin = await create_test_user(username="admin", is_superuser=True)
    user = await create_test_user(username="regular_user")

    assert admin.is_superuser is True
    assert user.is_superuser is False
```

#### `create_test_incident`
Factory fixture for creating incidents in test database.

```python
async def test_incident_workflow(db_session, create_test_incident):
    incident = await create_test_incident(
        title="Database connection pool exhausted",
        severity="critical"
    )
    assert incident.status == "open"
```

## Environment Variables

Configure test database connections via environment variables:

```bash
# Application database (default: localhost:5432)
export DATABASE_URL="postgresql+asyncpg://sentinel:sentinel@localhost:5432/sentinel_test"

# Vector database (default: localhost:5433)
export VECTORDB_URL="postgresql+asyncpg://vectoradmin:vectorpass@localhost:5433/vectordb_test"

# Redis (default: localhost:6379)
export REDIS_URL="redis://localhost:6379/0"
```

## Test Organization

```
tests/
├── conftest.py              # All fixtures defined here
├── unit/                    # Unit tests (isolated components)
│   ├── test_fixtures.py     # Fixture validation tests
│   ├── test_tools.py        # LangChain tool tests
│   └── test_routers.py      # API endpoint tests
└── integration/             # Integration tests (multiple components)
    ├── test_agent_graph.py  # LangGraph execution tests
    └── test_e2e.py          # End-to-end workflow tests
```

## Writing Tests

### Unit Test Example

```python
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

class TestUserRepository:
    async def test_create_user(self, db_session: AsyncSession):
        """Test user creation in database."""
        result = await db_session.execute(
            text("""
                INSERT INTO sentinel.users (username, email, hashed_password)
                VALUES ('testuser', 'test@example.com', 'hash')
                RETURNING id, username
            """)
        )
        user = result.fetchone()
        assert user.username == "testuser"
```

### Integration Test Example

```python
from httpx import AsyncClient
from unittest.mock import Mock

class TestIncidentWorkflow:
    async def test_create_and_analyze_incident(
        self,
        async_client: AsyncClient,
        mock_prometheus_client: Mock,
        mock_openai_llm: Mock,
    ):
        """Test full incident creation and analysis workflow."""
        # Create incident
        response = await async_client.post(
            "/api/incidents",
            json={"title": "High CPU", "severity": "critical"}
        )
        assert response.status_code == 201
        incident_id = response.json()["id"]

        # Trigger analysis (would normally call Celery task)
        analysis_response = await async_client.post(
            f"/api/incidents/{incident_id}/analyze"
        )
        assert analysis_response.status_code == 202
```

## Best Practices

1. **Use session-scoped fixtures for expensive resources** (database engines)
2. **Use function-scoped fixtures for test isolation** (database sessions)
3. **Always rollback database changes** (automatically handled by `db_session`)
4. **Mock external services** (Prometheus, LLMs, Redis) to avoid network calls
5. **Use factory fixtures** for creating test data with variations
6. **Test isolation** - each test should be independent and order-agnostic

## Running Tests in CI

The GitHub Actions workflow runs tests with service containers:

```yaml
services:
  postgres:
    image: postgres:16.2-alpine
    ports: ["5432:5432"]

  vectordb:
    image: pgvector/pgvector:pg16
    ports: ["5433:5433"]

  redis:
    image: redis:7.2-alpine
    ports: ["6379:6379"]
```

Tests run on Python 3.11 and 3.12 with coverage enforcement (80% minimum).
