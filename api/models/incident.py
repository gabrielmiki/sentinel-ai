"""
Incident model for tracking monitoring incidents.
"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from api.models.base import Base


class Incident(Base):
    """Incident model for tracking monitoring alerts and issues."""

    __tablename__ = "incidents"
    __table_args__ = {"schema": "sentinel"}

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid4()))
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="open", nullable=False)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("sentinel.users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(nullable=True)

    def __repr__(self) -> str:
        return f"<Incident(id={self.id}, title={self.title}, severity={self.severity})>"
