"""
Runbook model for storing operational procedures and documentation.
"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import ARRAY, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from api.models.base import VectorBase


class Runbook(VectorBase):
    """Runbook model for operational procedures and troubleshooting guides.

    Note: Stored in vectordb to enable efficient JOINs with embeddings table.
    """

    __tablename__ = "runbooks"
    __table_args__ = {"schema": "sentinel"}

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid4()))
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(String(100)), nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    chunk_count: Mapped[int | None] = mapped_column(default=0, nullable=True)
    source_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String, nullable=True)  # No FK - users table in different DB
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), default=datetime.now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        default=datetime.now,
        onupdate=datetime.now,
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<Runbook(id={self.id}, title={self.title})>"
