"""
SQLAlchemy declarative base for SentinelAI ORM models.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all application database models."""

    pass


class VectorBase(DeclarativeBase):
    """Base class for all vector database models."""

    pass
