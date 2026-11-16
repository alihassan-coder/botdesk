"""The handoffs migration (ADR 0014): a `tasks` table, and every bot gets the Team plugin switched
on. Down again, runs waiting for tasks are cancelled and the Team bindings go. Alembic on a
scratch SQLite file."""

import sqlite3
from pathlib import Path

from tests.test_migration_bindings import _alembic, _insert

BEFORE, AFTER = "c3d81f2a6b57", "4a7e2c9d1b03"


def test_upgrade_adds_tasks_and_a_team_binding_for_every_bot_and_downgrade_undoes_it(tmp_path: Path) -> None:
    database = tmp_path / "botdesk.db"
    _alembic(database, "upgrade", BEFORE)
    db = sqlite3.connect(database)
    user = _insert(db, "users", email="ali@acme.dev")
    org = _insert(db, "organizations")
    chief = _insert(db, "bots", org_id=org, created_by=user, handle="chief")
    sales = _insert(db, "bots", org_id=org, created_by=user, handle="sales")
    _insert(db, "bot_tools", org_id=org, bot_id=chief, plugin_id="demo", enabled=1)
    thread = _insert(db, "threads", org_id=org, kind="dm", bot_id=chief, created_by=user)
    db.commit()
    db.close()

    _alembic(database, "upgrade", AFTER)
    db = sqlite3.connect(database)
    bindings = set(db.execute("SELECT bot_id, plugin_id, enabled, connection_id FROM bot_tools"))
    assert bindings == {(chief, "demo", 1, None), (chief, "team", 1, None), (sales, "team", 1, None)}
    columns = [column[1] for column in db.execute("PRAGMA table_info(tasks)")]
    assert {"parent_run_id", "tool_call_id", "child_run_id", "deadline_at", "error_code"} <= set(columns)
    waiting = _insert(db, "runs", org_id=org, bot_id=chief, thread_id=thread, status="waiting_handoff")
    done = _insert(db, "runs", org_id=org, bot_id=chief, thread_id=thread, status="succeeded")
    db.commit()
    db.close()

    _alembic(database, "downgrade", BEFORE)
    db = sqlite3.connect(database)
    assert db.execute("SELECT name FROM sqlite_master WHERE name = 'tasks'").fetchall() == []
    assert set(db.execute("SELECT bot_id, plugin_id FROM bot_tools")) == {(chief, "demo")}
    statuses = dict(db.execute("SELECT id, status FROM runs"))
    assert statuses == {waiting: "cancelled", done: "succeeded"}
    db.close()
