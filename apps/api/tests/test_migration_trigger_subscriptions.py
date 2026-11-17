"""The trigger subscriptions migration (slice 6.3): one new table, gone again on the way down.
Alembic on a scratch SQLite file."""

import sqlite3
from pathlib import Path

from tests.test_migration_bindings import _alembic

BEFORE, AFTER = "b7d2f4a9c615", "e5a9c3f71d20"


def test_upgrade_adds_trigger_subscriptions_and_downgrade_drops_it(tmp_path: Path) -> None:
    database = tmp_path / "botdesk.db"
    _alembic(database, "upgrade", AFTER)
    db = sqlite3.connect(database)
    columns = {column[1] for column in db.execute("PRAGMA table_info(trigger_subscriptions)")}
    assert {"binding_id", "trigger", "subscriber_id", "connection_id", "cursor", "seen", "problem"} <= columns
    db.close()

    _alembic(database, "downgrade", BEFORE)
    db = sqlite3.connect(database)
    assert db.execute("SELECT name FROM sqlite_master WHERE name = 'trigger_subscriptions'").fetchall() == []
    db.close()
