"""
AgentRun model for tracking LangGraph execution history.
"""

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from api.models.base import Base


class AgentRun(Base):
    """AgentRun model for tracking LangGraph agent execution history."""

    __tablename__ = "agent_runs"
    __table_args__ = {"schema": "sentinel"}

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid4()))
    incident_id: Mapped[str | None] = mapped_column(
        ForeignKey("sentinel.incidents.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    input_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    output_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    current_node: Mapped[str | None] = mapped_column(String(100), nullable=True)
    completed_nodes: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True, default=list)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), default=datetime.now, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    def __repr__(self) -> str:
        return f"<AgentRun(id={self.id}, status={self.status}, incident_id={self.incident_id})>"
