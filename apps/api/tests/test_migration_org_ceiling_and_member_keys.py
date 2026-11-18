"""The two 2026-11-18 migrations, one after the other: the organization's security level ceiling
(`organizations.max_security_level`) and members' own model keys (`provider_credentials.user_id`).
Alembic on a scratch SQLite file, up then down."""

import sqlite3
from pathlib import Path

import pytest

from tests.test_migration_bindings import _alembic, _insert

BEFORE, CEILING, MEMBER_KEYS = "d4b8e1f0a372", "d5e1a7c3f920", "e8b3c6d2a417"


def _key(db: sqlite3.Connection, org: str, provider: str, **values: str) -> str:
    return _insert(db, "provider_credentials", org_id=org, provider=provider, encrypted_key="token", **values)


def test_existing_organizations_get_no_ceiling(tmp_path: Path) -> None:
    database = tmp_path / "botdesk.db"
    _alembic(database, "upgrade", BEFORE)
    db = sqlite3.connect(database)
    org = _insert(db, "organizations", default_security_level="read-only")
    db.commit()
    db.close()

    _alembic(database, "upgrade", CEILING)
    db = sqlite3.connect(database)
    assert db.execute("SELECT max_security_level FROM organizations WHERE id = ?", [org]).fetchone() == ("autonomous",)
    db.close()

    _alembic(database, "downgrade", BEFORE)
    db = sqlite3.connect(database)
    assert "max_security_level" not in [column[1] for column in db.execute("PRAGMA table_info(organizations)")]
    db.close()


def test_existing_keys_stay_the_organizations_and_members_get_one_each_per_provider(tmp_path: Path) -> None:
    database = tmp_path / "botdesk.db"
    _alembic(database, "upgrade", CEILING)
    db = sqlite3.connect(database)
    ali = _insert(db, "users", email="ali@acme.dev", handle="ali")
    sara = _insert(db, "users", email="sara@acme.dev", handle="sara")
    org = _insert(db, "organizations")
    org_key = _key(db, org, "openai", created_by=ali)
    _key(db, org, "custom", label="Ollama")
    _key(db, org, "custom", label="LM Studio")  # custom servers: as many as it likes
    db.commit()
    db.close()

    _alembic(database, "upgrade", MEMBER_KEYS)
    db = sqlite3.connect(database)
    assert db.execute("SELECT user_id FROM provider_credentials WHERE id = ?", [org_key]).fetchone() == (None,)
    # Beside the organization's OpenAI key: one of Sara's own, and one of Ali's.
    _key(db, org, "openai", user_id=sara)
    _key(db, org, "openai", user_id=ali)
    with pytest.raises(sqlite3.IntegrityError):
        _key(db, org, "openai", user_id=sara)  # a member has one key per provider
    with pytest.raises(sqlite3.IntegrityError):
        _key(db, org, "openai")  # and the organization still has one per built-in provider
    _key(db, org, "custom", label="vLLM")
    db.commit()
    db.close()

    _alembic(database, "downgrade", CEILING)
    db = sqlite3.connect(database)
    assert "user_id" not in [column[1] for column in db.execute("PRAGMA table_info(provider_credentials)")]
    # Members' own keys go (the old schema can't tell them apart); the organization's stay.
    rows = sorted(db.execute("SELECT provider, label FROM provider_credentials"))
    assert rows == [("custom", "LM Studio"), ("custom", "Ollama"), ("custom", "vLLM"), ("openai", "label")]
    with pytest.raises(sqlite3.IntegrityError):
        _key(db, org, "openai")
    _key(db, org, "custom", label="Jan")
    db.close()
