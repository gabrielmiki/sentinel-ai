"""
Runbook model for storing operational procedures and documentation.
"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import ARRAY, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from api.models.base import Base


class Runbook(Base):
    """Runbook model for operational procedures and troubleshooting guides."""

    __tablename__ = "runbooks"
    __table_args__ = {"schema": "sentinel"}

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid4()))
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(String(100)), nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("sentinel.users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<Runbook(id={self.id}, title={self.title})>"
