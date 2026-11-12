"""Alembic runs this for every migration command.

The database URL comes from the app's settings (DATABASE_URL in `.env`), never from
alembic.ini, so migrations always hit the same database as the API.
"""

import asyncio
from logging.config import fileConfig
from typing import Literal

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from src import models  # noqa: F401  (registers every table)
from src.core.config import get_settings
from src.core.database import Base, UtcDateTime

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
database_url = get_settings().sqlalchemy_url

# Tables other libraries create and manage themselves (LangGraph's checkpointer, mem0).
# Without this, autogenerate would offer to drop them.
FOREIGN_TABLES = {"checkpoints", "checkpoint_blobs", "checkpoint_writes", "checkpoint_migrations", "bot_memories"}


def include_object(obj: object, name: str | None, type_: str, reflected: bool, compare_to: object) -> bool:
    if type_ == "table" and reflected and compare_to is None and name in FOREIGN_TABLES:
        return False
    table = getattr(obj, "table", None)
    return not (type_ == "index" and reflected and table is not None and table.name in FOREIGN_TABLES)


def render_item(type_: str, obj: object, autogen_context: object) -> str | Literal[False]:
    """Write our UTC timestamp type into migrations as the plain column type it is."""
    if type_ == "type" and isinstance(obj, UtcDateTime):
        return "sa.DateTime(timezone=True)"
    return False


def run_migrations_offline() -> None:
    """`alembic upgrade head --sql`: print the SQL instead of running it."""
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
        include_object=include_object,
        render_item=render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    # Batch mode lets ALTER TABLE work on SQLite too (local default database).
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,
        include_object=include_object,
        render_item=render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(database_url)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online(), loop_factory=asyncio.SelectorEventLoop)
