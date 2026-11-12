"""Database setup: the model base class, the engine, and one session per request."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any, ClassVar

from fastapi import Request
from sqlalchemy import JSON, DateTime, MetaData, event
from sqlalchemy.dialects.postgresql import JSONB
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
    type_annotation_map: ClassVar[dict[Any, Any]] = {
        datetime: DateTime(timezone=True),
        # JSON lists (like a message's parts): JSONB on Postgres, plain JSON elsewhere.
        list[dict[str, Any]]: JSON().with_variant(JSONB(), "postgresql"),
        dict[str, Any]: JSON().with_variant(JSONB(), "postgresql"),
    }


class IdMixin:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


def _enforce_sqlite_foreign_keys(engine: AsyncEngine) -> None:
    """SQLite ignores foreign keys (and ON DELETE CASCADE) unless asked, unlike Postgres."""

    @event.listens_for(engine.sync_engine, "connect")
    def turn_on(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def postgres_connect_args(url: str) -> dict[str, Any]:
    """Behind a pooler (Neon's pooled hosts end in `-pooler`), one session's prepared statements
    can land on another session's connection, so psycopg must not prepare them."""
    return {"prepare_threshold": None} if "-pooler" in url else {}


def is_in_memory(url: str) -> bool:
    return url.startswith("sqlite") and (":memory:" in url or url.endswith("://"))


def create_engine(url: str) -> AsyncEngine:
    if not url.startswith("sqlite"):
        return create_async_engine(
            url,
            # Neon suspends after 5 idle minutes, which closes every connection. Replacing
            # connections older than 4 minutes means we never use one from before a suspend,
            # without `pool_pre_ping`'s extra round trip on every request.
            pool_recycle=240,
            pool_size=5,
            max_overflow=5,
            connect_args=postgres_connect_args(url),
        )
    in_memory = is_in_memory(url)
    # In memory: one shared connection, so the test database lives for the whole app.
    options: dict[str, Any] = (
        {"poolclass": StaticPool, "connect_args": {"check_same_thread": False}} if in_memory else {}
    )
    engine = create_async_engine(url, **options)
    _enforce_sqlite_foreign_keys(engine)
    return engine


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: a database session for this request. Services decide when to commit."""
    sessionmaker: async_sessionmaker[AsyncSession] = request.app.state.sessionmaker
    async with sessionmaker() as session:
        yield session
