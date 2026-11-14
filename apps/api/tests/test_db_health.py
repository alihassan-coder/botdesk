"""Connections that died while idle (Neon suspends after a few idle minutes and closes them) are
noticed before use: the request or run gets a fresh connection instead of an "SSL error:
unexpected eof". The Postgres tests kill a pooled connection's backend and use the pool again."""

import uuid
from typing import Any

import psycopg
import pytest
from sqlalchemy import text

from src.core.config import Settings
from src.core.database import POOL_MAX_LIFETIME_SECONDS, IdleCheck, create_engine
from src.runtime.memory import memory_pool
from src.runtime.runner import checkpoint_pool
from tests.conftest import TEST_DATABASE_URL


class FakeConnection:
    autocommit = True

    def __init__(self) -> None:
        self.pings = 0

    async def execute(self, query: str) -> None:
        self.pings += 1


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


async def test_a_connection_is_pinged_only_after_sitting_idle() -> None:
    clock, connection = Clock(), FakeConnection()
    check = IdleCheck(seconds=30, clock=clock)

    await check.check(connection)  # never seen by the pool's callbacks: nothing to go on
    await check.configure(connection)  # just opened, waiting in the pool
    clock.now += 31
    await check.check(connection)  # sat there too long: pinged
    assert connection.pings == 1
    connection.pings = 0

    await check.reset(connection)  # back in the pool
    clock.now += 10
    await check.check(connection)  # busy pool: no ping
    assert connection.pings == 0

    await check.reset(connection)
    clock.now += 31
    await check.check(connection)
    assert connection.pings == 1


def test_the_checkpoint_pool_checks_idle_connections() -> None:
    pool = checkpoint_pool("postgresql://u:p@localhost/db")
    assert isinstance(pool._check.__self__, IdleCheck)  # type: ignore[union-attr]
    assert isinstance(pool._reset.__self__, IdleCheck)  # type: ignore[union-attr]
    assert isinstance(pool._configure.__self__, IdleCheck)  # type: ignore[union-attr]
    assert pool.max_lifetime == pool.max_idle == POOL_MAX_LIFETIME_SECONDS < 300  # under Neon's suspend


def _postgres() -> Settings:
    if not TEST_DATABASE_URL:
        pytest.skip("Postgres test: set TEST_DATABASE_URL to run it (see docs/backend/README.md)")
    return Settings(database_url=TEST_DATABASE_URL, _env_file=None)


async def _kill(settings: Settings, pid: int) -> None:
    """End a backend from another connection, like Neon does when it suspends."""
    async with await psycopg.AsyncConnection.connect(settings.direct_url, autocommit=True) as other:
        await other.execute("SELECT pg_terminate_backend(%s)", (pid,))


async def test_the_engine_replaces_a_connection_that_died_while_idle() -> None:
    settings = _postgres()
    engine = create_engine(settings.sqlalchemy_url, idle_ping_seconds=0)
    try:
        async with engine.connect() as connection:
            pid = int((await connection.execute(text("SELECT pg_backend_pid()"))).scalar_one())
        await _kill(settings, pid)

        async with engine.connect() as connection:
            assert (await connection.execute(text("SELECT 1"))).scalar_one() == 1
    finally:
        await engine.dispose()


async def test_the_checkpoint_pool_replaces_a_connection_that_died_while_idle() -> None:
    settings = _postgres()
    pool: Any = checkpoint_pool(settings.direct_url, idle_check=IdleCheck(seconds=0))
    await pool.open(wait=True)
    try:
        async with pool.connection() as connection:
            pid = (await (await connection.execute("SELECT pg_backend_pid() AS pid")).fetchone())["pid"]
        await _kill(settings, pid)

        async with pool.connection() as connection:
            row = await (await connection.execute("SELECT %s::text AS x", (str(uuid.uuid4()),))).fetchone()
            assert row is not None
    finally:
        await pool.close()


async def test_mem0s_pool_replaces_a_connection_that_died_while_idle() -> None:
    settings = _postgres()
    pool = memory_pool(settings.direct_url, idle_check=IdleCheck(seconds=0))
    try:
        pool.wait()
        with pool.connection() as connection:
            row = connection.execute("SELECT pg_backend_pid()").fetchone()
            assert row is not None
        await _kill(settings, int(row[0]))

        with pool.connection() as connection:
            assert connection.execute("SELECT 1").fetchone() == (1,)
    finally:
        pool.close()
