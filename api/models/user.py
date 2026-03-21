"""
User model for authentication and authorization.
"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from api.models.base import Base


class User(Base):
    """User model for application authentication."""

    __tablename__ = "users"
    __table_args__ = {"schema": "sentinel"}

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid4()))
    username: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, server_default=text("true"), default=True, nullable=False
    )
    is_superuser: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false"), default=False, nullable=False
    )
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
        return f"<User(id={self.id}, username={self.username}, email={self.email})>"
