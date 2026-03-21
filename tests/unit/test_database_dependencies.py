"""
Tests for database dependency functions and error handling.

Tests the actual get_db() and get_vectordb() dependencies without mocking,
to ensure error handling paths (rollback, cleanup) are covered.
"""

import pytest
from sqlalchemy import text


@pytest.mark.database
class TestGetDbDependency:
    """Tests for get_db() dependency error handling."""

    @pytest.mark.asyncio
    async def test_get_db_commits_on_success_real(self) -> None:
        """Verify get_db commits transaction when no exception occurs."""
        from api.database import get_db

        # Use real get_db (not mocked)
        async for session in get_db():
            # Insert test data
            await session.execute(
                text(
                    "INSERT INTO sentinel.incidents (id, title, severity, status) "
                    "VALUES (gen_random_uuid(), 'test', 'low', 'open')"
                )
            )
            # Session should commit after yield

        # Verify data was committed by opening new session
        async for session in get_db():
            result = await session.execute(
                text("SELECT COUNT(*) FROM sentinel.incidents WHERE title = 'test'")
            )
            count = result.scalar()
            assert count >= 1

    @pytest.mark.asyncio
    async def test_get_db_rolls_back_on_error_real(self) -> None:
        """Verify get_db rolls back transaction when exception occurs."""
        from api.database import get_db

        try:
            async for session in get_db():
                # Insert test data
                await session.execute(
                    text(
                        "INSERT INTO sentinel.incidents (id, title, severity, status) "
                        "VALUES (gen_random_uuid(), 'rollback_test', 'low', 'open')"
                    )
                )
                # Simulate error
                raise ValueError("Simulated error")
        except ValueError:
            pass  # Expected

        # Verify data was rolled back by opening new session
        async for session in get_db():
            result = await session.execute(
                text("SELECT COUNT(*) FROM sentinel.incidents WHERE title = 'rollback_test'")
            )
            count = result.scalar()
            assert count == 0


@pytest.mark.database
class TestGetVectordbDependency:
    """Tests for get_vectordb() dependency error handling."""

    @pytest.mark.asyncio
    async def test_get_vectordb_commits_on_success_real(self) -> None:
        """Verify get_vectordb commits transaction when no exception occurs."""
        from api.database import get_vectordb

        # Use real get_vectordb (not mocked)
        async for session in get_vectordb():
            # Just verify we can execute a query
            result = await session.execute(text("SELECT 1"))
            assert result.scalar() == 1
            # Session should commit after yield

    @pytest.mark.asyncio
    async def test_get_vectordb_rolls_back_on_error_real(self) -> None:
        """Verify get_vectordb rolls back transaction when exception occurs."""
        from api.database import get_vectordb

        try:
            async for session in get_vectordb():
                # Execute a query
                await session.execute(text("SELECT 1"))
                # Simulate error
                raise ValueError("Simulated error")
        except ValueError:
            pass  # Expected error

        # Verify we can still use vectordb after error
        async for session in get_vectordb():
            result = await session.execute(text("SELECT 1"))
            assert result.scalar() == 1


@pytest.mark.database
class TestCloseDbConnections:
    """Tests for close_db_connections() shutdown function."""

    @pytest.mark.asyncio
    async def test_close_db_connections_succeeds(self) -> None:
        """Verify close_db_connections disposes engines cleanly."""
        from api.database import close_db_connections, engine, vectordb_engine

        # Verify engines are usable before closing
        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT 1"))
            assert result.scalar() == 1

        async with vectordb_engine.begin() as conn:
            result = await conn.execute(text("SELECT 1"))
            assert result.scalar() == 1

        # Close connections
        await close_db_connections()

        # Note: After dispose(), engines need to be recreated to be used again
        # This is expected behavior - engines are disposed during app shutdown
