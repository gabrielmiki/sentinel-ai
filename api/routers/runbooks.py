"""
Runbooks management router.

Handles runbook ingestion, chunking, embedding, and RAG search.
"""

import json
from datetime import datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db, get_vectordb

router = APIRouter(prefix="/api/v1/runbooks", tags=["runbooks"])


# ==================== Pydantic Schemas ====================


class RunbookIngestResponse(BaseModel):
    """Schema for runbook ingestion response."""

    runbook_id: str
    chunk_count: int
    message: str


class RunbookListItem(BaseModel):
    """Schema for runbook list item."""

    id: str
    title: str
    category: str | None
    tags: list[str] | None
    chunk_count: int | None
    source_filename: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class RunbookSearchRequest(BaseModel):
    """Schema for semantic search request."""

    query: str = Field(..., min_length=1)
    k: int = Field(5, ge=1, le=20, description="Number of results")


class RunbookSearchResult(BaseModel):
    """Schema for a single search result."""

    runbook_id: str
    content: str
    similarity_score: float
    metadata: dict[str, Any] | None = None


class RunbookSearchResponse(BaseModel):
    """Schema for search response."""

    query: str
    results: list[RunbookSearchResult]
    count: int


# ==================== Helper Functions ====================


def chunk_markdown(content: str, chunk_size: int = 1000, overlap: int = 200) -> list[str]:
    """
    Split markdown content into overlapping chunks.

    Args:
        content: Markdown text
        chunk_size: Target chunk size in characters
        overlap: Overlap between chunks

    Returns:
        List of text chunks
    """
    if len(content) <= chunk_size:
        return [content]

    chunks = []
    start = 0

    while start < len(content):
        end = start + chunk_size

        # Try to break at paragraph boundary
        if end < len(content):
            # Look for double newline (paragraph break)
            paragraph_break = content.rfind("\n\n", start, end)
            if paragraph_break > start:
                end = paragraph_break

        chunks.append(content[start:end].strip())
        start = end - overlap if end < len(content) else len(content)

    return chunks


async def generate_embeddings(texts: list[str]) -> list[list[float]]:
    """
    Generate embeddings using OpenAI API.

    Args:
        texts: List of text strings to embed

    Returns:
        List of embedding vectors
    """
    import os

    from langchain_openai import OpenAIEmbeddings
    from pydantic import SecretStr

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OPENAI_API_KEY not configured",
        )

    embeddings_model = OpenAIEmbeddings(model="text-embedding-ada-002", api_key=SecretStr(api_key))
    vectors = await embeddings_model.aembed_documents(texts)

    return vectors


# ==================== Endpoints ====================


@router.post(
    "/ingest",
    response_model=RunbookIngestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest runbook",
)
async def ingest_runbook(
    file: UploadFile = File(..., description="Markdown file"),
    db: AsyncSession = Depends(get_db),
    vectordb: AsyncSession = Depends(get_vectordb),
) -> dict[str, Any]:
    """
    Ingest a markdown runbook.

    Chunks the file, generates embeddings via OpenAI, and stores in pgvector.

    Args:
        file: Markdown file upload
        db: Application database session
        vectordb: Vector database session

    Returns:
        Runbook ID and chunk count
    """
    # Validate file type
    if not file.filename or not file.filename.endswith(".md"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only markdown (.md) files are supported",
        )

    # Read file content
    try:
        content = await file.read()
        text_content = content.decode("utf-8")
    except UnicodeDecodeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be valid UTF-8 encoded text",
        ) from e

    # Extract title from first heading or use filename
    title = file.filename.replace(".md", "")
    lines = text_content.split("\n")
    for line in lines:
        if line.startswith("# "):
            title = line[2:].strip()
            break

    # Create runbook record
    runbook_id = str(uuid4())
    create_query = text(
        """
        INSERT INTO sentinel.runbooks
        (id, title, content, source_filename, chunk_count)
        VALUES (:id, :title, :content, :filename, 0)
        RETURNING id
        """
    )

    await db.execute(
        create_query,
        {
            "id": runbook_id,
            "title": title,
            "content": text_content,
            "filename": file.filename,
        },
    )
    await db.commit()

    # Chunk the content
    chunks = chunk_markdown(text_content, chunk_size=1000, overlap=200)

    # Generate embeddings
    try:
        vectors = await generate_embeddings(chunks)
    except Exception as e:
        # Rollback runbook creation if embedding fails
        await db.execute(text("DELETE FROM sentinel.runbooks WHERE id = :id"), {"id": runbook_id})
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate embeddings: {e}",
        ) from e

    # Insert embeddings into vectordb
    insert_query = text(
        """
        INSERT INTO embeddings.runbook_embeddings
        (id, runbook_id, content, embedding, meta)
        VALUES (:id, :runbook_id, :content, :embedding, :meta)
        """
    )

    for i, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True)):
        await vectordb.execute(
            insert_query,
            {
                "id": str(uuid4()),
                "runbook_id": runbook_id,
                "content": chunk,
                "embedding": str(vector),  # Convert list to string for pgvector
                "meta": json.dumps(
                    {"chunk_index": i, "source_file": file.filename}
                ),  # Convert dict to JSON string for JSONB
            },
        )

    await vectordb.commit()

    # Update chunk count
    await db.execute(
        text("UPDATE sentinel.runbooks SET chunk_count = :count WHERE id = :id"),
        {"count": len(chunks), "id": runbook_id},
    )
    await db.commit()

    return {
        "runbook_id": runbook_id,
        "chunk_count": len(chunks),
        "message": f"Successfully ingested {file.filename} with {len(chunks)} chunks",
    }


@router.get(
    "/",
    response_model=list[RunbookListItem],
    summary="List runbooks",
)
async def list_runbooks(
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    List all indexed runbooks with metadata.

    Args:
        db: Database session

    Returns:
        List of runbooks
    """
    from api.models.runbook import Runbook

    query = select(Runbook).order_by(Runbook.created_at.desc())
    result = await db.execute(query)
    runbooks = result.scalars().all()

    return runbooks


@router.delete(
    "/{runbook_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete runbook",
)
async def delete_runbook(
    runbook_id: str,
    db: AsyncSession = Depends(get_db),
    vectordb: AsyncSession = Depends(get_vectordb),
) -> None:
    """
    Delete runbook and all associated chunks from vector store.

    Args:
        runbook_id: Runbook ID
        db: Application database
        vectordb: Vector database
    """
    from api.models.runbook import Runbook
    from api.models.vector import RunbookEmbedding

    # Verify runbook exists
    query = select(Runbook).where(Runbook.id == runbook_id)
    result = await db.execute(query)
    runbook = result.scalar_one_or_none()

    if not runbook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Runbook {runbook_id} not found",
        )

    # Delete embeddings from vectordb
    delete_embeddings = delete(RunbookEmbedding).where(RunbookEmbedding.runbook_id == runbook_id)
    await vectordb.execute(delete_embeddings)
    await vectordb.commit()

    # Delete runbook
    delete_runbook = delete(Runbook).where(Runbook.id == runbook_id)
    await db.execute(delete_runbook)
    await db.commit()


@router.post(
    "/search",
    response_model=RunbookSearchResponse,
    summary="Search runbooks",
)
async def search_runbooks(
    search_request: RunbookSearchRequest,
    vectordb: AsyncSession = Depends(get_vectordb),
) -> dict[str, Any]:
    """
    Semantic search across runbook chunks using pgvector.

    Returns k most relevant chunks with similarity scores for RAG diagnostics.

    Args:
        search_request: Search query and parameters
        vectordb: Vector database session

    Returns:
        Ranked search results with similarity scores
    """
    # Generate query embedding
    try:
        query_vectors = await generate_embeddings([search_request.query])
        query_vector = query_vectors[0]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate query embedding: {e}",
        ) from e

    # Perform vector similarity search
    # Use CAST to avoid ambiguity with SQLAlchemy parameter binding
    search_query = text(
        """
        SELECT
            runbook_id,
            content,
            meta,
            1 - (embedding <=> CAST(:query_vector AS vector)) as similarity
        FROM embeddings.runbook_embeddings
        WHERE embedding IS NOT NULL
        ORDER BY embedding <=> CAST(:query_vector AS vector)
        LIMIT :k
        """
    )

    result = await vectordb.execute(
        search_query,
        {
            "query_vector": str(query_vector),  # Convert list to string for pgvector
            "k": search_request.k,
        },
    )

    rows = result.fetchall()

    results = [
        {
            "runbook_id": row[0],
            "content": row[1],
            "metadata": row[2],
            "similarity_score": float(row[3]),
        }
        for row in rows
    ]

    return {
        "query": search_request.query,
        "results": results,
        "count": len(results),
    }
