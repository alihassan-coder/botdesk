"""Connections on real Postgres: JSONB scopes, the owner check constraint and the expression-based
unique index (one row per account per owner, NULL owner ids included). Straight on the database,
without the app: the HTTP side is covered on SQLite in test_connections.py."""

import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings
from src.core.database import create_engine, create_sessionmaker
from src.models import Connection, Organization
from tests.conftest import TEST_DATABASE_URL, _empty_database


@pytest.fixture
async def db() -> AsyncIterator[AsyncSession]:
    if not TEST_DATABASE_URL:
        pytest.skip("Postgres test: set TEST_DATABASE_URL to run it (see docs/backend/README.md)")
    await _empty_database(TEST_DATABASE_URL)
    engine = create_engine(Settings(database_url=TEST_DATABASE_URL, _env_file=None).sqlalchemy_url)
    async with create_sessionmaker(engine)() as session:
        yield session
    await engine.dispose()


def _connection(org_id: uuid.UUID, **changes: object) -> Connection:
    row = Connection(
        org_id=org_id,
        connector_id="demo",
        owner_kind="org",
        auth_type="api_key",
        account_label="Shared",
        account_ref="shared",
        scopes=["read"],
        encrypted_secret="x",
    )
    for key, value in changes.items():
        setattr(row, key, value)
    return row


async def test_one_row_per_account_and_owner_and_a_valid_owner_on_postgres(db: AsyncSession) -> None:
    org = Organization(name="Acme", slug=f"acme-{uuid.uuid4().hex[:8]}")
    db.add(org)
    await db.flush()
    org_id = org.id
    db.add(_connection(org_id))
    await db.commit()

    db.add(_connection(org_id))  # the same org-owned account again (both owner ids NULL)
    with pytest.raises(IntegrityError):
        await db.commit()
    await db.rollback()

    db.add(_connection(org_id, account_ref="other", owner_bot_id=uuid.uuid4()))  # org-owned with an owner
    with pytest.raises(IntegrityError):
        await db.commit()
    await db.rollback()

    db.add(_connection(org_id, account_ref="second"))  # another account is fine
    await db.commit()
