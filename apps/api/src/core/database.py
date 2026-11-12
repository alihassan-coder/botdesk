"""Database setup: the model base class, the engine, and one session per request."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any, ClassVar

from fastapi import Request
from sqlalchemy import DateTime, MetaData
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import StaticPool

# Stable constraint names, so Alembic migrations are predictable.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def utcnow() -> datetime:
    return datetime.now(UTC)


def as_utc(moment: datetime) -> datetime:
    """SQLite hands back naive datetimes; treat them as UTC."""
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map: ClassVar[dict[Any, Any]] = {datetime: DateTime(timezone=True)}


class IdMixin:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


def create_engine(url: str) -> AsyncEngine:
    in_memory_sqlite = url.startswith("sqlite") and (":memory:" in url or url.endswith("://"))
    if in_memory_sqlite:
        # One shared connection, so an in-memory test database lives for the whole app.
        return create_async_engine(url, poolclass=StaticPool, connect_args={"check_same_thread": False})
    return create_async_engine(url, pool_pre_ping=True)


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: a database session for this request. Services decide when to commit."""
    sessionmaker: async_sessionmaker[AsyncSession] = request.app.state.sessionmaker
    async with sessionmaker() as session:
        yield session
