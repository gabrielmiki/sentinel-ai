"""
Database configuration and session management for SentinelAI.

Provides:
- Async SQLAlchemy engines for PostgreSQL (app data) and pgvector (embeddings)
- Session factories
- FastAPI dependency functions for database sessions
"""

import os
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Database URLs from environment variables
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://sentinel:sentinel@postgres:5432/sentinel",
)
VECTORDB_URL = os.getenv(
    "VECTORDB_URL",
    "postgresql+asyncpg://vectoradmin:vectorpass@vectordb:5432/vectordb",
)

# Create async engines
engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    pool_recycle=3600,
)

vectordb_engine: AsyncEngine = create_async_engine(
    VECTORDB_URL,
    echo=False,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    pool_recycle=3600,
)

# Create session factories
AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

AsyncVectorSessionLocal = sessionmaker(
    vectordb_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency for application database sessions.

    Yields async session with automatic cleanup and error handling.

    Usage:
        @app.get("/users")
        async def get_users(db: AsyncSession = Depends(get_db)):
            result = await db.execute(select(User))
            return result.scalars().all()
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_vectordb() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency for vector database sessions.

    Yields async session for pgvector operations with automatic cleanup.

    Usage:
        @app.post("/embeddings/search")
        async def search_embeddings(
            query: str,
            vectordb: AsyncSession = Depends(get_vectordb)
        ):
            result = await vectordb.execute(
                select(Embedding).where(...)
            )
            return result.scalars().all()
    """
    async with AsyncVectorSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def close_db_connections() -> None:
    """
    Close all database connections gracefully.

    Call during application shutdown to ensure clean connection pool disposal.
    """
    await engine.dispose()
    await vectordb_engine.dispose()
