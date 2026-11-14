"""Database setup: the model base class, the engine, and one session per request."""

import time
import uuid
import weakref
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from typing import Any, ClassVar

from fastapi import Request
from psycopg_pool import AsyncConnectionPool, ConnectionPool
from sqlalchemy import JSON, DateTime, Dialect, MetaData, TypeDecorator, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import DisconnectionError
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


class UtcDateTime(TypeDecorator[datetime]):
    """A timestamp that is always UTC with an offset, on every database.

    Postgres keeps the zone (timestamptz); SQLite stores plain text and hands back naive
    datetimes, which would reach the API as "2026-11-12T10:00:00" with no "+00:00". So values
    are turned into UTC before they're saved (comparisons like `created_at < :before` then
    line up on SQLite too) and marked UTC when they're read.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        return as_utc(value) if value is not None else None


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map: ClassVar[dict[Any, Any]] = {
        datetime: UtcDateTime(),
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


# Neon suspends after 5 idle minutes and closes every connection; networks drop idle TLS
# connections too. A connection that sat unused this long is tested before it's used again
# (one short round trip), so a dead one is replaced instead of failing the request or run.
# Busy connections are never tested: no extra round trip while the app is in use.
IDLE_PING_SECONDS = 10.0
# psycopg_pool pools also replace connections this old, or idle this long (beyond `min_size`),
# like SQLAlchemy's `pool_recycle`: both under Neon's 5 minutes. (Its defaults are 1 h and 10 min.)
POOL_MAX_LIFETIME_SECONDS = 240.0
_IDLE_SINCE = "botdesk_idle_since"


def _ping_after_idle(engine: AsyncEngine, seconds: float) -> None:
    """SQLAlchemy's `pool_pre_ping`, but only for connections idle at least `seconds`: on checkout
    such a connection runs `SELECT 1`, and if that fails the pool connects again (raising
    `DisconnectionError` from a checkout listener is SQLAlchemy's documented way to ask for that)."""

    @event.listens_for(engine.sync_engine, "checkin")
    def returned(_dbapi_connection: Any, record: Any) -> None:
        record.info[_IDLE_SINCE] = time.monotonic()

    @event.listens_for(engine.sync_engine, "checkout")
    def check(dbapi_connection: Any, record: Any, _proxy: Any) -> None:
        idle_since = record.info.get(_IDLE_SINCE)  # none on a new connection (`info` goes with it)
        if idle_since is None or time.monotonic() - idle_since < seconds:
            return
        try:
            engine.dialect.do_ping(dbapi_connection)
        except Exception as error:
            raise DisconnectionError(f"connection died while idle: {error}") from error


def create_engine(url: str, *, idle_ping_seconds: float = IDLE_PING_SECONDS) -> AsyncEngine:
    if not url.startswith("sqlite"):
        engine = create_async_engine(
            url,
            # Replace connections older than 4 minutes, so most never reach Neon's 5-minute
            # suspend; the idle check below catches the ones that die anyway.
            pool_recycle=240,
            pool_size=5,
            max_overflow=5,
            connect_args=postgres_connect_args(url),
        )
        _ping_after_idle(engine, idle_ping_seconds)
        return engine
    in_memory = is_in_memory(url)
    # In memory: one shared connection, so the test database lives for the whole app.
    options: dict[str, Any] = (
        {"poolclass": StaticPool, "connect_args": {"check_same_thread": False}} if in_memory else {}
    )
    engine = create_async_engine(url, **options)
    _enforce_sqlite_foreign_keys(engine)
    return engine


class IdleCheck:
    """The same idea for psycopg_pool pools (LangGraph's checkpoints, mem0): pass `configure`,
    `check` and `reset` to the pool. `configure` and `reset` note when a connection opened or came
    back; `check` runs psycopg_pool's own `check_connection` (an empty query) only on a connection
    idle at least `seconds`. A failed check makes the pool discard that connection and hand out
    another."""

    def __init__(self, seconds: float = IDLE_PING_SECONDS, clock: Callable[[], float] = time.monotonic) -> None:
        self.seconds = seconds
        self.clock = clock
        self._returned_at: weakref.WeakKeyDictionary[Any, float] = weakref.WeakKeyDictionary()

    def _idle_too_long(self, connection: Any) -> bool:
        returned_at = self._returned_at.pop(connection, None)
        return returned_at is not None and self.clock() - returned_at >= self.seconds

    async def reset(self, connection: Any) -> None:
        self._returned_at[connection] = self.clock()

    # A new connection counts as returned when it opens: one that waits in the pool long enough
    # (the first one, opened at startup) is checked like any other.
    configure = reset

    async def check(self, connection: Any) -> None:
        if self._idle_too_long(connection):
            await AsyncConnectionPool.check_connection(connection)

    def reset_sync(self, connection: Any) -> None:
        self._returned_at[connection] = self.clock()

    configure_sync = reset_sync

    def check_sync(self, connection: Any) -> None:
        if self._idle_too_long(connection):
            ConnectionPool.check_connection(connection)


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: a database session for this request. Services decide when to commit."""
    sessionmaker: async_sessionmaker[AsyncSession] = request.app.state.sessionmaker
    async with sessionmaker() as session:
        yield session
