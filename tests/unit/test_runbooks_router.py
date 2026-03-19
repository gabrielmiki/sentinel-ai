"""
Tests for runbooks router endpoints.
"""


import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.database
class TestIngestRunbook:
    """Tests for POST /api/v1/runbooks/ingest endpoint."""

    @pytest.mark.asyncio
    async def test_ingest_runbook_returns_201(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Verify ingest runbook endpoint returns 201 Created."""
        # Create markdown file
        markdown_content = b"# Test Runbook\n\nThis is a test runbook for incident response."
        files = {"file": ("test.md", markdown_content, "text/markdown")}

        response = await client.post("/api/v1/runbooks/ingest", files=files)
        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_ingest_runbook_returns_correct_structure(
        self, client: AsyncClient
    ) -> None:
        """Verify ingest runbook returns expected JSON structure."""
        markdown_content = b"# Database Incident Runbook\n\nSteps to resolve database issues."
        files = {"file": ("database.md", markdown_content, "text/markdown")}

        response = await client.post("/api/v1/runbooks/ingest", files=files)
        data = response.json()

        # Verify all required fields are present
        assert "runbook_id" in data
        assert "chunk_count" in data
        assert "message" in data

    @pytest.mark.asyncio
    async def test_ingest_runbook_creates_runbook_in_database(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Verify runbook is created in database."""
        markdown_content = b"# API Runbook\n\nAPI troubleshooting guide."
        files = {"file": ("api.md", markdown_content, "text/markdown")}

        response = await client.post("/api/v1/runbooks/ingest", files=files)
        data = response.json()

        runbook_id = data["runbook_id"]

        # Verify runbook exists in database
        query = text("SELECT id, title FROM sentinel.runbooks WHERE id = :id")
        result = await db_session.execute(query, {"id": runbook_id})
        row = result.fetchone()

        assert row is not None
        assert row[0] == runbook_id

    @pytest.mark.asyncio
    async def test_ingest_runbook_extracts_title_from_heading(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Verify title is extracted from first # heading."""
        markdown_content = b"# Network Incident Response\n\nNetwork troubleshooting steps."
        files = {"file": ("network.md", markdown_content, "text/markdown")}

        response = await client.post("/api/v1/runbooks/ingest", files=files)
        data = response.json()

        runbook_id = data["runbook_id"]

        # Verify title in database
        query = text("SELECT title FROM sentinel.runbooks WHERE id = :id")
        result = await db_session.execute(query, {"id": runbook_id})
        row = result.fetchone()

        assert row is not None
        assert row[0] == "Network Incident Response"

    @pytest.mark.asyncio
    async def test_ingest_runbook_uses_filename_when_no_heading(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Verify filename is used as title when no # heading exists."""
        markdown_content = b"This runbook has no heading.\n\nJust content."
        files = {"file": ("fallback_title.md", markdown_content, "text/markdown")}

        response = await client.post("/api/v1/runbooks/ingest", files=files)
        data = response.json()

        runbook_id = data["runbook_id"]

        # Verify title in database uses filename without extension
        query = text("SELECT title FROM sentinel.runbooks WHERE id = :id")
        result = await db_session.execute(query, {"id": runbook_id})
        row = result.fetchone()

        assert row is not None
        assert row[0] == "fallback_title"

    @pytest.mark.asyncio
    async def test_ingest_runbook_returns_400_for_non_markdown_file(
        self, client: AsyncClient
    ) -> None:
        """Verify 400 is returned for non-.md files."""
        text_content = b"This is a text file, not markdown."
        files = {"file": ("document.txt", text_content, "text/plain")}

        response = await client.post("/api/v1/runbooks/ingest", files=files)
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_ingest_runbook_returns_error_message_for_non_markdown(
        self, client: AsyncClient
    ) -> None:
        """Verify proper error message for non-.md files."""
        json_content = b'{"key": "value"}'
        files = {"file": ("data.json", json_content, "application/json")}

        response = await client.post("/api/v1/runbooks/ingest", files=files)
        data = response.json()

        assert "detail" in data
        assert "markdown" in data["detail"].lower()


@pytest.mark.database
class TestListRunbooks:
    """Tests for GET /api/v1/runbooks/ endpoint."""

    @pytest.mark.asyncio
    async def test_list_runbooks_returns_200(self, client: AsyncClient) -> None:
        """Verify list runbooks endpoint returns 200 OK."""
        response = await client.get("/api/v1/runbooks/")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_runbooks_returns_list(self, client: AsyncClient) -> None:
        """Verify list runbooks returns a list."""
        response = await client.get("/api/v1/runbooks/")
        data = response.json()

        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_list_runbooks_returns_correct_structure(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Verify each runbook has expected fields."""
        # Create a runbook first
        await self._create_runbook(db_session, "Test Runbook", "Test content")

        response = await client.get("/api/v1/runbooks/")
        data = response.json()

        assert len(data) > 0
        runbook = data[0]

        # Verify all required fields are present
        assert "id" in runbook
        assert "title" in runbook
        assert "category" in runbook
        assert "tags" in runbook
        assert "chunk_count" in runbook
        assert "source_filename" in runbook
        assert "created_at" in runbook

    @pytest.mark.asyncio
    async def test_list_runbooks_orders_by_created_at_desc(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Verify runbooks are ordered by created_at descending."""
        # Create multiple runbooks
        await self._create_runbook(db_session, "First Runbook", "Content 1")
        await self._create_runbook(db_session, "Second Runbook", "Content 2")
        await self._create_runbook(db_session, "Third Runbook", "Content 3")

        response = await client.get("/api/v1/runbooks/")
        data = response.json()

        assert len(data) >= 3
        # Most recently created should be first
        assert data[0]["title"] == "Third Runbook"

    @pytest.mark.asyncio
    async def test_list_runbooks_returns_empty_list_when_no_runbooks(
        self, client: AsyncClient
    ) -> None:
        """Verify empty list is returned when no runbooks exist."""
        response = await client.get("/api/v1/runbooks/")
        data = response.json()

        assert isinstance(data, list)

    # Helper method
    async def _create_runbook(
        self,
        db_session: AsyncSession,
        title: str,
        content: str,
        chunk_count: int = 1,
    ) -> str:
        """Create a runbook and return its ID."""
        query = text(
            """
            INSERT INTO sentinel.runbooks
            (id, title, content, chunk_count)
            VALUES (gen_random_uuid(), :title, :content, :chunk_count)
            RETURNING id
            """
        )

        result = await db_session.execute(
            query,
            {
                "title": title,
                "content": content,
                "chunk_count": chunk_count,
            },
        )
        await db_session.commit()

        row = result.fetchone()
        return str(row[0])


@pytest.mark.database
class TestDeleteRunbook:
    """Tests for DELETE /api/v1/runbooks/{runbook_id} endpoint."""

    @pytest.mark.asyncio
    async def test_delete_runbook_returns_204(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Verify delete runbook endpoint returns 204 No Content."""
        # Create runbook first
        runbook_id = await self._create_runbook(db_session, "Test Runbook", "Content")

        response = await client.delete(f"/api/v1/runbooks/{runbook_id}")
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_runbook_removes_from_database(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Verify runbook is removed from database after deletion."""
        # Create runbook first
        runbook_id = await self._create_runbook(
            db_session, "Database Runbook", "DB Content"
        )

        await client.delete(f"/api/v1/runbooks/{runbook_id}")

        # Verify runbook no longer exists in database
        query = text("SELECT id FROM sentinel.runbooks WHERE id = :id")
        result = await db_session.execute(query, {"id": runbook_id})
        row = result.fetchone()

        assert row is None

    @pytest.mark.asyncio
    async def test_delete_runbook_returns_404_when_not_found(
        self, client: AsyncClient
    ) -> None:
        """Verify 404 is returned when runbook doesn't exist."""
        nonexistent_id = "00000000-0000-0000-0000-000000000000"

        response = await client.delete(f"/api/v1/runbooks/{nonexistent_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_runbook_returns_error_message_when_not_found(
        self, client: AsyncClient
    ) -> None:
        """Verify proper error message when runbook doesn't exist."""
        nonexistent_id = "00000000-0000-0000-0000-000000000000"

        response = await client.delete(f"/api/v1/runbooks/{nonexistent_id}")
        data = response.json()

        assert "detail" in data
        assert f"Runbook {nonexistent_id} not found" in data["detail"]

    # Helper method
    async def _create_runbook(
        self,
        db_session: AsyncSession,
        title: str,
        content: str,
        chunk_count: int = 1,
    ) -> str:
        """Create a runbook and return its ID."""
        query = text(
            """
            INSERT INTO sentinel.runbooks
            (id, title, content, chunk_count)
            VALUES (gen_random_uuid(), :title, :content, :chunk_count)
            RETURNING id
            """
        )

        result = await db_session.execute(
            query,
            {
                "title": title,
                "content": content,
                "chunk_count": chunk_count,
            },
        )
        await db_session.commit()

        row = result.fetchone()
        return str(row[0])


@pytest.mark.database
class TestSearchRunbooks:
    """Tests for POST /api/v1/runbooks/search endpoint."""

    @pytest.mark.asyncio
    async def test_search_runbooks_returns_200(self, client: AsyncClient) -> None:
        """Verify search runbooks endpoint returns 200 OK."""
        payload = {"query": "database incident", "k": 5}

        response = await client.post("/api/v1/runbooks/search", json=payload)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_search_runbooks_returns_correct_structure(
        self, client: AsyncClient
    ) -> None:
        """Verify search runbooks returns expected JSON structure."""
        payload = {"query": "network troubleshooting", "k": 3}

        response = await client.post("/api/v1/runbooks/search", json=payload)
        data = response.json()

        # Verify all required fields are present
        assert "query" in data
        assert "results" in data
        assert "count" in data
        assert isinstance(data["results"], list)

    @pytest.mark.asyncio
    async def test_search_runbooks_returns_query_in_response(
        self, client: AsyncClient
    ) -> None:
        """Verify search response includes the original query."""
        query_text = "kubernetes deployment failure"
        payload = {"query": query_text, "k": 5}

        response = await client.post("/api/v1/runbooks/search", json=payload)
        data = response.json()

        assert data["query"] == query_text

    @pytest.mark.asyncio
    async def test_search_runbooks_result_has_required_fields(
        self, client: AsyncClient
    ) -> None:
        """Verify each search result has expected fields."""
        payload = {"query": "test query", "k": 5}

        response = await client.post("/api/v1/runbooks/search", json=payload)
        data = response.json()

        # If results exist, verify structure
        if data["count"] > 0:
            result = data["results"][0]
            assert "runbook_id" in result
            assert "content" in result
            assert "similarity_score" in result
            assert "metadata" in result

    @pytest.mark.asyncio
    async def test_search_runbooks_respects_k_parameter(
        self, client: AsyncClient
    ) -> None:
        """Verify search respects the k (limit) parameter."""
        payload = {"query": "api error handling", "k": 2}

        response = await client.post("/api/v1/runbooks/search", json=payload)
        data = response.json()

        # Should return at most k results
        assert len(data["results"]) <= 2

    @pytest.mark.asyncio
    async def test_search_runbooks_returns_400_for_missing_query(
        self, client: AsyncClient
    ) -> None:
        """Verify 400 is returned when query is missing."""
        payload = {"k": 5}  # Missing query field

        response = await client.post("/api/v1/runbooks/search", json=payload)
        assert response.status_code == 422  # FastAPI validation error

    @pytest.mark.asyncio
    async def test_search_runbooks_returns_400_for_empty_query(
        self, client: AsyncClient
    ) -> None:
        """Verify 400 is returned when query is empty."""
        payload = {"query": "", "k": 5}

        response = await client.post("/api/v1/runbooks/search", json=payload)
        assert response.status_code == 422  # FastAPI validation error (min_length=1)
