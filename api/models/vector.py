"""
Vector database models for storing embeddings.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from api.models.base import VectorBase


class RunbookEmbedding(VectorBase):
    """Runbook embedding model for RAG retrieval."""

    __tablename__ = "runbook_embeddings"
    __table_args__ = {"schema": "embeddings"}

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid4()))
    runbook_id: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[Any | None] = mapped_column(Vector(1536), nullable=True)
    meta: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC), nullable=False)

    def __repr__(self) -> str:
        return f"<RunbookEmbedding(id={self.id}, runbook_id={self.runbook_id})>"


class IncidentEmbedding(VectorBase):
    """Incident embedding model for similarity search."""

    __tablename__ = "incident_embeddings"
    __table_args__ = {"schema": "embeddings"}

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid4()))
    incident_id: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[Any | None] = mapped_column(Vector(1536), nullable=True)
    meta: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC), nullable=False)

    def __repr__(self) -> str:
        return f"<IncidentEmbedding(id={self.id}, incident_id={self.incident_id})>"
