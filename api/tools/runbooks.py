"""
Runbook search tool for semantic similarity search.

Provides async function to search runbook embeddings using vector similarity.
"""

import json
import os
from typing import Any

from langchain_openai import OpenAIEmbeddings
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from api.tools.prometheus import ToolExecutionError


class Document(BaseModel):
    """LangChain-compatible document with content and metadata."""

    page_content: str = Field(description="Document content")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Document metadata")


async def generate_embeddings(texts: list[str]) -> list[list[float]]:
    """
    Generate embeddings for text using OpenAI.

    Args:
        texts: List of text strings to embed

    Returns:
        List of embedding vectors

    Raises:
        ToolExecutionError: If embedding generation fails
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ToolExecutionError("OPENAI_API_KEY not configured")

    try:
        embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        return await embeddings.aembed_documents(texts)
    except Exception as e:
        raise ToolExecutionError(f"Failed to generate embeddings: {e}") from e


async def _search_runbooks(
    query: str, k: int = 3, engine: AsyncEngine | None = None
) -> list[Document]:
    """
    Search runbooks using semantic similarity.

    Args:
        query: Search query string
        k: Number of results to return (default 3)
        engine: AsyncEngine for vectordb (optional, uses default if None)

    Returns:
        List of Document objects with content and metadata

    Raises:
        ToolExecutionError: If search fails
    """
    try:
        # Generate embedding for query
        query_embeddings = await generate_embeddings([query])
        query_vector = query_embeddings[0]

        # Use provided engine or import default
        if engine is None:
            from api.database import vectordb_engine

            engine = vectordb_engine

        async with engine.connect() as conn:
            # Perform similarity search
            search_query = text(
                """
                SELECT
                    c.runbook_id,
                    c.content,
                    c.meta,
                    r.title,
                    1 - (c.embedding <=> CAST(:query_vector AS vector)) AS similarity_score
                FROM embeddings.runbook_chunks c
                JOIN sentinel.runbooks r ON c.runbook_id = r.id
                WHERE 1 - (c.embedding <=> CAST(:query_vector AS vector)) > 0.5
                ORDER BY c.embedding <=> CAST(:query_vector AS vector)
                LIMIT :k
                """
            )

            result = await conn.execute(
                search_query,
                {"query_vector": str(query_vector), "k": k},
            )

            rows = result.fetchall()

            # Convert to Document objects
            documents = []
            for row in rows:
                meta = json.loads(row.meta) if row.meta else {}
                meta["title"] = row.title
                meta["runbook_id"] = row.runbook_id
                meta["score"] = float(row.similarity_score)

                documents.append(
                    Document(
                        page_content=row.content,
                        metadata=meta,
                    )
                )

            return documents

    except Exception as e:
        if isinstance(e, ToolExecutionError):
            raise
        raise ToolExecutionError(f"Runbook search failed: {e}") from e
