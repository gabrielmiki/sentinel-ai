"""
Tests for database dependency functions (api/database.py).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestGetDbDependency:
    """Test get_db FastAPI dependency."""

    @pytest.mark.asyncio
    async def test_get_db_yields_session(self) -> None:
        """Verify get_db dependency is an async generator."""
        from api.database import get_db

        # Verify it's an async generator function
        gen = get_db()
        assert hasattr(gen, "__anext__")

    @pytest.mark.asyncio
    async def test_get_db_commits_on_success(self) -> None:
        """Verify get_db commits transaction on successful completion."""
        from api.database import get_db

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.close = AsyncMock()

        with patch("api.database.AsyncSessionLocal") as mock_session_maker:
            mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_maker.return_value.__aexit__ = AsyncMock()

            async for _ in get_db():
                pass  # Normal completion

            # Verify commit was called
            mock_session.commit.assert_called_once()
            mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_db_rolls_back_on_error(self) -> None:
        """Verify get_db rolls back transaction on exception."""
        from api.database import get_db

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock(side_effect=ValueError("Database error"))
        mock_session.rollback = AsyncMock()
        mock_session.close = AsyncMock()

        with patch("api.database.AsyncSessionLocal") as mock_session_maker:
            mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_maker.return_value.__aexit__ = AsyncMock()

            try:
                async for _ in get_db():
                    pass  # Commit will raise error
            except ValueError:
                pass  # Expected error from commit

            # Verify rollback was called when commit failed
            mock_session.rollback.assert_called_once()
            mock_session.close.assert_called_once()


class TestGetVectordbDependency:
    """Test get_vectordb FastAPI dependency."""

    @pytest.mark.asyncio
    async def test_get_vectordb_yields_session(self) -> None:
        """Verify get_vectordb dependency is an async generator."""
        from api.database import get_vectordb

        # Verify it's an async generator function
        gen = get_vectordb()
        assert hasattr(gen, "__anext__")

    @pytest.mark.asyncio
    async def test_get_vectordb_commits_on_success(self) -> None:
        """Verify get_vectordb commits transaction on successful completion."""
        from api.database import get_vectordb

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.close = AsyncMock()

        with patch("api.database.AsyncVectorSessionLocal") as mock_session_maker:
            mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_maker.return_value.__aexit__ = AsyncMock()

            async for _ in get_vectordb():
                pass  # Normal completion

            # Verify commit was called
            mock_session.commit.assert_called_once()
            mock_session.close.assert_called_once()


class TestCloseDbConnections:
    """Test database connection cleanup."""

    @pytest.mark.asyncio
    async def test_close_db_connections_disposes_engines(self) -> None:
        """Verify close_db_connections disposes both engines."""
        from api.database import close_db_connections

        # Mock the engines at the module level
        mock_engine = MagicMock()
        mock_engine.dispose = AsyncMock()
        mock_vectordb = MagicMock()
        mock_vectordb.dispose = AsyncMock()

        with (
            patch("api.database.engine", mock_engine),
            patch("api.database.vectordb_engine", mock_vectordb),
        ):
            await close_db_connections()

            # Verify both engines were disposed
            mock_engine.dispose.assert_called_once()
            mock_vectordb.dispose.assert_called_once()


class TestDatabaseConfiguration:
    """Test database engine and session factory configuration."""

    def test_engine_exists(self) -> None:
        """Verify main database engine is created."""
        from api.database import engine

        assert engine is not None
        assert engine.url.drivername == "postgresql+asyncpg"

    def test_vectordb_engine_exists(self) -> None:
        """Verify vector database engine is created."""
        from api.database import vectordb_engine

        assert vectordb_engine is not None
        assert vectordb_engine.url.drivername == "postgresql+asyncpg"

    def test_session_factories_exist(self) -> None:
        """Verify async session factories are created."""
        from api.database import AsyncSessionLocal, AsyncVectorSessionLocal

        assert AsyncSessionLocal is not None
        assert AsyncVectorSessionLocal is not None
