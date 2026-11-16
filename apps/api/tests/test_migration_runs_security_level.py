"""The runs.security_level migration: runs a routine already started keep the routine's level, so
removing the routine later can't loosen them. Alembic on a scratch SQLite file, up then down."""

import sqlite3
from pathlib import Path

from tests.test_migration_bindings import _alembic, _insert

BEFORE, AFTER = "8cf59be5197c", "c3d81f2a6b57"


def test_upgrade_keeps_each_routine_runs_level_on_the_run(tmp_path: Path) -> None:
    database = tmp_path / "botdesk.db"
    _alembic(database, "upgrade", BEFORE)
    db = sqlite3.connect(database)
    user = _insert(db, "users", email="ali@acme.dev")
    org = _insert(db, "organizations")
    bot = _insert(db, "bots", org_id=org, created_by=user, handle="scout")
    thread = _insert(db, "threads", org_id=org, kind="dm", bot_id=bot, created_by=user)
    strict = _insert(db, "routines", org_id=org, bot_id=bot, created_by=user, security_level="read-only")
    plain = _insert(db, "routines", org_id=org, bot_id=bot, created_by=user, security_level=None)
    by_strict = _insert(db, "runs", org_id=org, bot_id=bot, thread_id=thread)
    by_plain = _insert(db, "runs", org_id=org, bot_id=bot, thread_id=thread)
    by_person = _insert(db, "runs", org_id=org, bot_id=bot, thread_id=thread)
    _insert(db, "routine_runs", routine_id=strict, run_id=by_strict)
    _insert(db, "routine_runs", routine_id=plain, run_id=by_plain)
    db.commit()
    db.close()

    _alembic(database, "upgrade", AFTER)
    db = sqlite3.connect(database)
    levels = dict(db.execute("SELECT id, security_level FROM runs"))
    assert levels == {by_strict: "read-only", by_plain: None, by_person: None}
    db.close()

    _alembic(database, "downgrade", BEFORE)
    db = sqlite3.connect(database)
    assert "security_level" not in [column[1] for column in db.execute("PRAGMA table_info(runs)")]
    db.close()
